from contextlib import asynccontextmanager
from typing import Any, AsyncIterator
import os
import time
import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy import text

from .config import Settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


async def build_engine(settings: Settings, max_retries: int = 5, initial_delay: float = 1.0) -> AsyncEngine:
    """
    Build database engine with automatic retry logic and exponential backoff.

    Args:
        settings: Application settings
        max_retries: Maximum number of connection attempts
        initial_delay: Initial delay between retries in seconds

    Returns:
        Configured AsyncEngine instance

    Raises:
        ConnectionError: If unable to connect after all retries
    """
    retries = 0
    last_error = None

    while retries < max_retries:
        try:
            # Optimize for better performance on old Android devices
            engine = create_async_engine(
                settings.database.url,
                echo=False,
                future=True,
                pool_size=int(os.environ.get("DB_POOL_SIZE", "5")),  # Configurable pool size
                max_overflow=int(os.environ.get("DB_MAX_OVERFLOW", "10")),  # Configurable overflow
                pool_pre_ping=True,  # Check connections before use
                pool_recycle=int(os.environ.get("DB_POOL_RECYCLE", "3600")),  # Configurable connection recycling
                # Add connection timeout settings
                connect_args={
                    "connect_timeout": int(os.environ.get("DB_CONNECT_TIMEOUT", "10")),
                    "command_timeout": int(os.environ.get("DB_COMMAND_TIMEOUT", "30")),
                } if "sqlite" not in settings.database.url else {}
            )

            # Test the connection
            async with engine.begin() as conn:
                await conn.execute(text("SELECT 1"))

            logger.info(f"Database connected successfully on attempt {retries + 1}")
            return engine

        except OperationalError as e:
            last_error = e
            retries += 1

            if retries >= max_retries:
                logger.error(f"Failed to connect to database after {max_retries} attempts")
                break

            # Exponential backoff with jitter
            delay = initial_delay * (2 ** (retries - 1))
            jitter = delay * 0.1 * (0.5 + asyncio.get_event_loop().time() % 1)
            total_delay = delay + jitter

            logger.warning(
                f"Database connection failed (attempt {retries}/{max_retries}). "
                f"Retrying in {total_delay:.1f}s... Error: {str(e)[:100]}"
            )

            await asyncio.sleep(total_delay)

        except Exception as e:
            last_error = e
            logger.error(f"Unexpected database connection error: {e}")
            break

    # If we get here, all retries failed
    raise ConnectionError(f"Failed to connect to database after {max_retries} attempts. Last error: {last_error}")


def build_engine_sync(settings: Settings) -> AsyncEngine:
    """
    Synchronous version of build_engine for backwards compatibility.
    Wraps the async version in a new event loop.
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(build_engine(settings))


def build_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def session_scope(session_factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    """
    Enhanced session scope with retry logic and better error handling.

    Args:
        session_factory: SQLAlchemy async session factory

    Yields:
        AsyncSession: Database session with automatic commit/rollback
    """
    session = session_factory()
    try:
        yield session
        await session.commit()
    except OperationalError as e:
        logger.warning(f"Database operation failed, attempting rollback: {e}")
        await session.rollback()
        raise
    except SQLAlchemyError as e:
        logger.error(f"Database error occurred: {e}")
        await session.rollback()
        raise
    except Exception as e:
        logger.error(f"Unexpected error in database session: {e}")
        await session.rollback()
        raise
    finally:
        await session.close()


@asynccontextmanager
async def resilient_session_scope(session_factory: async_sessionmaker[AsyncSession],
                                 max_retries: int = 3,
                                 operations: list[str] = None) -> AsyncIterator[AsyncSession]:
    """
    Resilient session scope with automatic retry for failed operations.

    Args:
        session_factory: SQLAlchemy async session factory
        max_retries: Maximum number of retry attempts
        operations: List of operation names to retry (empty = all operations)

    Yields:
        AsyncSession: Database session with retry logic
    """
    retries = 0
    last_error = None

    while retries < max_retries:
        session = session_factory()
        try:
            yield session
            await session.commit()
            return  # Success, exit retry loop

        except OperationalError as e:
            last_error = e
            retries += 1

            if retries >= max_retries:
                logger.error(f"Database operation failed after {max_retries} retries: {e}")
                await session.rollback()
                break

            logger.warning(f"Database operation failed (attempt {retries}/{max_retries}), retrying: {e}")
            await session.rollback()
            await asyncio.sleep(1 * retries)  # Incremental backoff

        except SQLAlchemyError as e:
            # Don't retry non-operational SQL errors
            logger.error(f"Non-retryable database error: {e}")
            await session.rollback()
            raise
        except Exception as e:
            # Don't retry non-database errors
            logger.error(f"Non-database error in session: {e}")
            await session.rollback()
            raise
        finally:
            await session.close()

    # If we get here, all retries failed
    raise ConnectionError(f"Database operation failed after {max_retries} retries. Last error: {last_error}")


async def execute_with_retry(session: AsyncSession,
                           operation,
                           max_retries: int = 3,
                           delay: float = 1.0) -> Any:
    """
    Execute a database operation with automatic retry logic.

    Args:
        session: Database session
        operation: Async callable that takes the session as argument
        max_retries: Maximum number of retry attempts
        delay: Initial delay between retries

    Returns:
        Result of the operation

    Raises:
        ConnectionError: If operation fails after all retries
    """
    retries = 0
    last_error = None

    while retries < max_retries:
        try:
            return await operation(session)

        except OperationalError as e:
            last_error = e
            retries += 1

            if retries >= max_retries:
                logger.error(f"Database operation failed after {max_retries} retries: {e}")
                break

            # Exponential backoff with jitter
            wait_time = delay * (2 ** (retries - 1))
            jitter = wait_time * 0.1 * (0.5 + asyncio.get_event_loop().time() % 1)
            total_delay = wait_time + jitter

            logger.warning(f"Database operation failed (attempt {retries}/{max_retries}), retrying in {total_delay:.1f}s: {e}")
            await asyncio.sleep(total_delay)

        except Exception as e:
            # Don't retry non-database errors
            raise

    raise ConnectionError(f"Database operation failed after {max_retries} retries. Last error: {last_error}")


async def init_models(engine: AsyncEngine, max_retries: int = 3) -> None:
    """
    Initialize database models with retry logic.

    Args:
        engine: Database engine
        max_retries: Maximum number of retry attempts
    """
    retries = 0
    last_error = None

    while retries < max_retries:
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Database models initialized successfully")
            return

        except OperationalError as e:
            last_error = e
            retries += 1

            if retries >= max_retries:
                logger.error(f"Failed to initialize database models after {max_retries} attempts: {e}")
                break

            logger.warning(f"Database model initialization failed (attempt {retries}/{max_retries}), retrying: {e}")
            await asyncio.sleep(2 ** retries)  # Exponential backoff

        except Exception as e:
            logger.error(f"Unexpected error initializing database models: {e}")
            raise

    raise ConnectionError(f"Failed to initialize database models after {max_retries} attempts. Last error: {last_error}")


async def health_check(engine: AsyncEngine) -> dict:
    """
    Perform a health check on the database connection.

    Args:
        engine: Database engine to check

    Returns:
        Dictionary with health check results
    """
    try:
        start_time = time.time()
        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT 1 as health_check"))
            result.first()

        response_time = (time.time() - start_time) * 1000

        return {
            'status': 'healthy',
            'response_time_ms': round(response_time, 2),
            'message': 'Database connection successful'
        }

    except OperationalError as e:
        return {
            'status': 'unhealthy',
            'response_time_ms': None,
            'message': f'Database connection failed: {str(e)}'
        }
    except Exception as e:
        return {
            'status': 'error',
            'response_time_ms': None,
            'message': f'Database health check error: {str(e)}'
        }
