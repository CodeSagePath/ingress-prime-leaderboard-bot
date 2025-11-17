#!/usr/bin/env python3
"""
Retry Decorators for Telegram API Calls - Ingress Prime Leaderboard Bot
Provides robust retry logic for handling rate limiting, network errors, and timeouts
"""

import time
import logging
import asyncio
import functools
import random
from typing import Callable, Any, Optional, Union, Type, Tuple
from datetime import datetime, timedelta

try:
    from telegram.error import (
        TimedOut, NetworkError, RetryAfter,
        BadRequest, ChatMigrated, Conflict, TelegramError
    )
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    # Create dummy exceptions for environments without telegram
    class TelegramError(Exception):
        pass
    class TimedOut(TelegramError):
        pass
    class NetworkError(TelegramError):
        pass
    class RetryAfter(TelegramError):
        def __init__(self, retry_after):
            self.retry_after = retry_after
            super().__init__(f"Flood control exceeded. Retry in {retry_after} seconds")
    class BadRequest(TelegramError):
        pass
    class ChatMigrated(TelegramError):
        pass
    class Conflict(TelegramError):
        pass

logger = logging.getLogger(__name__)


class RetryConfig:
    """Configuration for retry behavior"""

    def __init__(self,
                 max_retries: int = 3,
                 base_delay: float = 1.0,
                 max_delay: float = 60.0,
                 exponential_base: float = 2.0,
                 jitter: bool = True,
                 jitter_factor: float = 0.1):
        """
        Initialize retry configuration.

        Args:
            max_retries: Maximum number of retry attempts
            base_delay: Base delay between retries in seconds
            max_delay: Maximum delay between retries in seconds
            exponential_base: Base for exponential backoff
            jitter: Whether to add jitter to delays
            jitter_factor: Fraction of delay to jitter (0.0 to 0.5)
        """
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
        self.jitter_factor = jitter_factor


class RetryStats:
    """Statistics for retry operations"""

    def __init__(self):
        self.total_attempts = 0
        self.successful_attempts = 0
        self.failed_attempts = 0
        self.retry_count = 0
        self.total_delay_time = 0.0
        self.errors_by_type = {}

    def record_attempt(self, success: bool, delay: float = 0.0, error_type: Optional[str] = None):
        """Record an attempt"""
        self.total_attempts += 1
        self.total_delay_time += delay

        if success:
            self.successful_attempts += 1
        else:
            self.failed_attempts += 1
            if error_type:
                self.errors_by_type[error_type] = self.errors_by_type.get(error_type, 0) + 1

    def record_retry(self):
        """Record a retry attempt"""
        self.retry_count += 1

    def get_success_rate(self) -> float:
        """Get success rate as percentage"""
        if self.total_attempts == 0:
            return 0.0
        return (self.successful_attempts / self.total_attempts) * 100

    def get_average_delay(self) -> float:
        """Get average delay time"""
        if self.retry_count == 0:
            return 0.0
        return self.total_delay_time / self.retry_count


# Global statistics
_retry_stats = RetryStats()


def get_retry_stats() -> dict:
    """Get global retry statistics"""
    return {
        'total_attempts': _retry_stats.total_attempts,
        'successful_attempts': _retry_stats.successful_attempts,
        'failed_attempts': _retry_stats.failed_attempts,
        'retry_count': _retry_stats.retry_count,
        'success_rate': _retry_stats.get_success_rate(),
        'average_delay': _retry_stats.get_average_delay(),
        'errors_by_type': _retry_stats.errors_by_type.copy()
    }


def reset_retry_stats():
    """Reset global retry statistics"""
    global _retry_stats
    _retry_stats = RetryStats()


def calculate_delay(attempt: int, config: RetryConfig) -> float:
    """
    Calculate delay for retry attempt with exponential backoff and jitter.

    Args:
        attempt: Current attempt number (0-based)
        config: Retry configuration

    Returns:
        Delay time in seconds
    """
    # Exponential backoff
    delay = config.base_delay * (config.exponential_base ** attempt)
    delay = min(delay, config.max_delay)

    # Add jitter if enabled
    if config.jitter:
        jitter_amount = delay * config.jitter_factor
        jitter = random.uniform(-jitter_amount, jitter_amount)
        delay += jitter

    return max(0, delay)  # Ensure non-negative


def is_retryable_error(error: Exception) -> Tuple[bool, Optional[float]]:
    """
    Determine if an error is retryable and return retry delay if applicable.

    Args:
        error: Exception to check

    Returns:
        Tuple of (is_retryable, retry_delay_in_seconds)
    """
    if not TELEGRAM_AVAILABLE:
        # For non-telegram environments, retry network-like errors
        if isinstance(error, (ConnectionError, TimeoutError)):
            return True, None
        return False, None

    # Telegram-specific error handling
    if isinstance(error, RetryAfter):
        # Telegram tells us exactly how long to wait
        return True, error.retry_after

    elif isinstance(error, (TimedOut, NetworkError)):
        # Network and timeout errors are generally retryable
        return True, None

    elif isinstance(error, Conflict):
        # Conflicts can be retryable (e.g., bot was restarted)
        return True, 5.0  # Wait 5 seconds for conflicts

    elif isinstance(error, ChatMigrated):
        # Chat migration might need retry with new chat ID
        return True, None

    elif isinstance(error, BadRequest):
        # Bad requests are generally not retryable, but some specific cases are
        error_msg = str(error).lower()
        if any(keyword in error_msg for keyword in ['timeout', 'retry', 'try again']):
            return True, None
        return False, None

    elif isinstance(error, TelegramError):
        # Generic telegram errors - check message for retryable indicators
        error_msg = str(error).lower()
        retryable_keywords = ['timeout', 'network', 'retry', 'try again', 'too many requests']
        if any(keyword in error_msg for keyword in retryable_keywords):
            return True, None
        return False, None

    # Generic errors
    elif isinstance(error, (ConnectionError, TimeoutError)):
        return True, None

    return False, None


def telegram_retry_async(config: Optional[RetryConfig] = None,
                             error_types: Optional[Tuple[Type[Exception], ...]] = None):
    """
    Async decorator for retrying Telegram API calls with exponential backoff.

    Args:
        config: Retry configuration (uses default if None)
        error_types: Specific error types to retry (empty = all retryable)
    """
    if config is None:
        config = RetryConfig()

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            last_error = None
            start_time = time.time()

            for attempt in range(config.max_retries + 1):
                try:
                    result = await func(*args, **kwargs)

                    # Success - record and return
                    if attempt > 0:
                        delay_time = time.time() - start_time
                        _retry_stats.record_attempt(success=True, delay=delay_time)
                        logger.debug(f"Function '{func.__name__}' succeeded after {attempt} retries")

                    _retry_stats.record_attempt(success=True)
                    return result

                except Exception as error:
                    last_error = error

                    # Check if error is retryable
                    is_retryable, specific_delay = is_retryable_error(error)

                    # If specific error types are specified, check against them
                    if error_types and not isinstance(error, error_types):
                        is_retryable = False

                    if not is_retryable or attempt >= config.max_retries:
                        # Not retryable or max retries reached
                        _retry_stats.record_attempt(success=False, error_type=type(error).__name__)
                        logger.error(f"Function '{func.__name__}' failed permanently: {error}")
                        raise

                    # Calculate delay
                    if specific_delay is not None:
                        delay = specific_delay
                        logger.warning(f"Rate limited for function '{func.__name__}'. Waiting {delay}s as requested by Telegram")
                    else:
                        delay = calculate_delay(attempt, config)
                        logger.warning(f"Function '{func.__name__}' failed (attempt {attempt + 1}/{config.max_retries + 1}): {error}. Retrying in {delay:.1f}s...")

                    # Record retry
                    _retry_stats.record_retry()

                    # Wait before retry
                    await asyncio.sleep(delay)

            # This should never be reached, but just in case
            _retry_stats.record_attempt(success=False, error_type=type(last_error).__name__)
            raise last_error

        return async_wrapper

    return decorator


def telegram_retry_sync(config: Optional[RetryConfig] = None,
                       error_types: Optional[Tuple[Type[Exception], ...]] = None):
    """
    Sync decorator for retrying Telegram API calls with exponential backoff.

    Args:
        config: Retry configuration (uses default if None)
        error_types: Specific error types to retry (empty = all retryable)
    """
    if config is None:
        config = RetryConfig()

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            last_error = None
            start_time = time.time()

            for attempt in range(config.max_retries + 1):
                try:
                    result = func(*args, **kwargs)

                    # Success - record and return
                    if attempt > 0:
                        delay_time = time.time() - start_time
                        _retry_stats.record_attempt(success=True, delay=delay_time)
                        logger.debug(f"Function '{func.__name__}' succeeded after {attempt} retries")

                    _retry_stats.record_attempt(success=True)
                    return result

                except Exception as error:
                    last_error = error

                    # Check if error is retryable
                    is_retryable, specific_delay = is_retryable_error(error)

                    # If specific error types are specified, check against them
                    if error_types and not isinstance(error, error_types):
                        is_retryable = False

                    if not is_retryable or attempt >= config.max_retries:
                        # Not retryable or max retries reached
                        _retry_stats.record_attempt(success=False, error_type=type(error).__name__)
                        logger.error(f"Function '{func.__name__}' failed permanently: {error}")
                        raise

                    # Calculate delay
                    if specific_delay is not None:
                        delay = specific_delay
                        logger.warning(f"Rate limited for function '{func.__name__}'. Waiting {delay}s as requested by Telegram")
                    else:
                        delay = calculate_delay(attempt, config)
                        logger.warning(f"Function '{func.__name__}' failed (attempt {attempt + 1}/{config.max_retries + 1}): {error}. Retrying in {delay:.1f}s...")

                    # Record retry
                    _retry_stats.record_retry()

                    # Wait before retry
                    time.sleep(delay)

            # This should never be reached, but just in case
            _retry_stats.record_attempt(success=False, error_type=type(last_error).__name__)
            raise last_error

        return sync_wrapper

    return decorator


# Convenience decorators for common use cases
def telegram_message_retry(max_retries: int = 3):
    """
    Retry decorator specifically for message sending operations.
    """
    config = RetryConfig(
        max_retries=max_retries,
        base_delay=0.5,
        max_delay=30.0,
        exponential_base=2.0,
        jitter=True
    )
    return telegram_retry_async(config)


def telegram_polling_retry(max_retries: int = 5):
    """
    Retry decorator specifically for polling operations.
    """
    config = RetryConfig(
        max_retries=max_retries,
        base_delay=2.0,
        max_delay=60.0,
        exponential_base=1.5,
        jitter=True
    )
    return telegram_retry_async(config)


def telegram_file_retry(max_retries: int = 2):
    """
    Retry decorator specifically for file operations (more conservative).
    """
    config = RetryConfig(
        max_retries=max_retries,
        base_delay=1.0,
        max_delay=10.0,
        exponential_base=2.0,
        jitter=False  # No jitter for file operations
    )
    return telegram_retry_async(config)


class CircuitBreaker:
    """
    Circuit breaker pattern for handling repeated failures
    """

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 60.0):
        """
        Initialize circuit breaker.

        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Time to wait before attempting recovery
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = 'CLOSED'  # CLOSED, OPEN, HALF_OPEN

    def __call__(self, func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            if self.state == 'OPEN':
                if time.time() - self.last_failure_time > self.recovery_timeout:
                    self.state = 'HALF_OPEN'
                    logger.info(f"Circuit breaker for '{func.__name__}' entering HALF_OPEN state")
                else:
                    raise TelegramError(f"Circuit breaker OPEN for '{func.__name__}'. Too many failures.")

            try:
                result = await func(*args, **kwargs)
                # Success - reset circuit breaker
                if self.state != 'CLOSED':
                    self.state = 'CLOSED'
                    self.failure_count = 0
                    logger.info(f"Circuit breaker for '{func.__name__}' reset to CLOSED")
                return result

            except Exception as e:
                self.failure_count += 1
                self.last_failure_time = time.time()

                if self.failure_count >= self.failure_threshold:
                    self.state = 'OPEN'
                    logger.warning(f"Circuit breaker for '{func.__name__}' OPENED after {self.failure_count} failures")

                raise

        return wrapper


# Example usage decorator combining retry and circuit breaker
def resilient_telegram_call(max_retries: int = 3, failure_threshold: int = 5):
    """
    Combined decorator with both retry logic and circuit breaker.
    """
    def decorator(func):
        retry_decorator = telegram_retry_async(RetryConfig(max_retries=max_retries))
        circuit_breaker = CircuitBreaker(failure_threshold=failure_threshold)
        return circuit_breaker(retry_decorator(func))
    return decorator