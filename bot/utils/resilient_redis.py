#!/usr/bin/env python3
"""
Resilient Redis Connection Module for Ingress Prime Leaderboard Bot
Provides Redis connectivity with fallback to in-memory cache
"""

import time
import logging
import threading
from typing import Optional, Any, Union
import json
from datetime import datetime, timedelta

try:
    import redis
    from redis.exceptions import ConnectionError, TimeoutError, RedisError
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None
    ConnectionError = TimeoutError = RedisError = Exception

logger = logging.getLogger(__name__)


class ResilientRedis:
    """
    Redis connection with automatic fallback to in-memory cache.
    Provides seamless operation even when Redis is unavailable.
    """

    def __init__(self, redis_url: str, timeout: int = 5, max_retries: int = 3):
        """
        Initialize resilient Redis client.

        Args:
            redis_url: Redis connection URL
            timeout: Connection timeout in seconds
            max_retries: Maximum number of connection attempts
        """
        self.redis_url = redis_url
        self.timeout = timeout
        self.max_retries = max_retries
        self.redis_client = None
        self.in_memory_cache = {}  # Fallback cache
        self.in_memory_cache_expiry = {}  # Expiry timestamps for fallback cache
        self.using_fallback = False
        self.last_connection_attempt = None
        self.connection_retry_interval = 60  # Seconds between reconnection attempts
        self.cache_lock = threading.RLock()  # Thread safety for fallback cache

        # Try to establish initial connection
        self._connect()

        # Start background thread for cache cleanup
        self._start_cache_cleanup()

    def _connect(self) -> bool:
        """
        Attempt to establish Redis connection.

        Returns:
            True if connection successful, False otherwise
        """
        if not REDIS_AVAILABLE:
            logger.warning("Redis module not available, using in-memory fallback only")
            self.using_fallback = True
            return False

        retries = 0
        last_error = None

        while retries < self.max_retries:
            try:
                logger.info(f"Attempting Redis connection (attempt {retries + 1}/{self.max_retries})")

                self.redis_client = redis.from_url(
                    self.redis_url,
                    socket_timeout=self.timeout,
                    socket_connect_timeout=self.timeout,
                    retry_on_timeout=True,
                    decode_responses=True,
                    health_check_interval=30
                )

                # Test connection
                self.redis_client.ping()

                # Test basic operations
                test_key = "health_check_test"
                self.redis_client.setex(test_key, 10, "test")
                test_result = self.redis_client.get(test_key)
                self.redis_client.delete(test_key)

                if test_result == "test":
                    logger.info("Redis connection established successfully")
                    self.using_fallback = False
                    self.last_connection_attempt = datetime.now()
                    return True
                else:
                    raise ConnectionError("Redis connection test failed")

            except (ConnectionError, TimeoutError, RedisError) as e:
                last_error = e
                retries += 1

                if retries >= self.max_retries:
                    break

                wait_time = min(2 ** retries, 10)  # Exponential backoff, max 10s
                logger.warning(
                    f"Redis connection failed (attempt {retries}/{self.max_retries}), "
                    f"retrying in {wait_time}s: {str(e)[:100]}"
                )
                time.sleep(wait_time)

            except Exception as e:
                last_error = e
                logger.error(f"Unexpected error connecting to Redis: {e}")
                break

        logger.error(f"Failed to connect to Redis after {self.max_retries} attempts: {last_error}")
        self.using_fallback = True
        self.redis_client = None
        return False

    def _should_retry_connection(self) -> bool:
        """
        Check if we should attempt to reconnect to Redis.

        Returns:
            True if reconnection attempt should be made
        """
        if not self.using_fallback:
            return True

        if self.last_connection_attempt is None:
            return True

        time_since_last_attempt = datetime.now() - self.last_connection_attempt
        return time_since_last_attempt.total_seconds() >= self.connection_retry_interval

    def _ensure_connection(self) -> bool:
        """
        Ensure Redis connection is active, attempt reconnection if needed.

        Returns:
            True if Redis is available
        """
        if self.redis_client is not None and not self.using_fallback:
            try:
                # Quick health check
                self.redis_client.ping()
                return True
            except (ConnectionError, TimeoutError, RedisError):
                logger.warning("Redis connection lost, switching to fallback mode")
                self.using_fallback = True
                self.redis_client = None

        # Try to reconnect if it's been a while
        if self._should_retry_connection():
            return self._connect()

        return False

    def _start_cache_cleanup(self):
        """Start background thread for cleanup of expired items in fallback cache."""
        def cleanup_expired():
            while True:
                try:
                    current_time = datetime.now()
                    expired_keys = []

                    with self.cache_lock:
                        for key, expiry_time in self.in_memory_cache_expiry.items():
                            if current_time > expiry_time:
                                expired_keys.append(key)

                        for key in expired_keys:
                            self.in_memory_cache.pop(key, None)
                            self.in_memory_cache_expiry.pop(key, None)

                    if expired_keys:
                        logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")

                except Exception as e:
                    logger.error(f"Error in cache cleanup: {e}")

                time.sleep(60)  # Clean up every minute

        cleanup_thread = threading.Thread(target=cleanup_expired, daemon=True)
        cleanup_thread.start()
        logger.debug("Started cache cleanup background thread")

    def get(self, key: str) -> Optional[str]:
        """
        Get value from Redis or fallback cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found
        """
        # Try Redis first
        if self._ensure_connection():
            try:
                value = self.redis_client.get(key)
                if value is not None:
                    logger.debug(f"Cache hit (Redis): {key}")
                    return value
            except Exception as e:
                logger.warning(f"Redis get failed for key '{key}': {e}")
                self.using_fallback = True

        # Fallback to in-memory cache
        with self.cache_lock:
            if key in self.in_memory_cache:
                expiry_time = self.in_memory_cache_expiry.get(key)
                if expiry_time is None or datetime.now() < expiry_time:
                    logger.debug(f"Cache hit (memory): {key}")
                    return self.in_memory_cache[key]
                else:
                    # Expired, remove it
                    del self.in_memory_cache[key]
                    if key in self.in_memory_cache_expiry:
                        del self.in_memory_cache_expiry[key]

        logger.debug(f"Cache miss: {key}")
        return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        Set value in Redis or fallback cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds (None for no expiry)

        Returns:
            True if successful
        """
        # Try Redis first
        if self._ensure_connection():
            try:
                if ttl is not None:
                    result = self.redis_client.setex(key, ttl, str(value))
                else:
                    result = self.redis_client.set(key, str(value))

                if result:
                    logger.debug(f"Cache set (Redis): {key}")
                    return True
            except Exception as e:
                logger.warning(f"Redis set failed for key '{key}': {e}")
                self.using_fallback = True

        # Fallback to in-memory cache
        with self.cache_lock:
            self.in_memory_cache[key] = str(value)
            if ttl is not None:
                self.in_memory_cache_expiry[key] = datetime.now() + timedelta(seconds=ttl)
            elif key in self.in_memory_cache_expiry:
                del self.in_memory_cache_expiry[key]

            logger.debug(f"Cache set (memory): {key}")
            return True

    def delete(self, key: str) -> bool:
        """
        Delete key from Redis or fallback cache.

        Args:
            key: Cache key to delete

        Returns:
            True if key was deleted or didn't exist
        """
        deleted = False

        # Try Redis first
        if self._ensure_connection():
            try:
                result = self.redis_client.delete(key)
                deleted = result > 0
                if deleted:
                    logger.debug(f"Cache delete (Redis): {key}")
            except Exception as e:
                logger.warning(f"Redis delete failed for key '{key}': {e}")
                self.using_fallback = True

        # Always try to delete from fallback cache
        with self.cache_lock:
            memory_deleted = key in self.in_memory_cache
            self.in_memory_cache.pop(key, None)
            self.in_memory_cache_expiry.pop(key, None)

            if memory_deleted:
                logger.debug(f"Cache delete (memory): {key}")
                deleted = True

        return deleted

    def exists(self, key: str) -> bool:
        """
        Check if key exists in Redis or fallback cache.

        Args:
            key: Cache key

        Returns:
            True if key exists
        """
        # Try Redis first
        if self._ensure_connection():
            try:
                exists = self.redis_client.exists(key)
                if exists:
                    logger.debug(f"Cache exists (Redis): {key}")
                    return True
            except Exception as e:
                logger.warning(f"Redis exists check failed for key '{key}': {e}")
                self.using_fallback = True

        # Check fallback cache
        with self.cache_lock:
            if key in self.in_memory_cache:
                expiry_time = self.in_memory_cache_expiry.get(key)
                if expiry_time is None or datetime.now() < expiry_time:
                    logger.debug(f"Cache exists (memory): {key}")
                    return True
                else:
                    # Expired, remove it
                    del self.in_memory_cache[key]
                    if key in self.in_memory_cache_expiry:
                        del self.in_memory_cache_expiry[key]

        return False

    def increment(self, key: str, amount: int = 1) -> Optional[int]:
        """
        Increment value atomically.

        Args:
            key: Cache key
            amount: Amount to increment by

        Returns:
            New value or None if operation failed
        """
        # Try Redis first
        if self._ensure_connection():
            try:
                result = self.redis_client.incrby(key, amount)
                logger.debug(f"Cache increment (Redis): {key} by {amount} = {result}")
                return result
            except Exception as e:
                logger.warning(f"Redis increment failed for key '{key}': {e}")
                self.using_fallback = True

        # Fallback to in-memory (not atomic, but best effort)
        with self.cache_lock:
            current_value = self.in_memory_cache.get(key, "0")
            try:
                int_value = int(current_value) + amount
                self.in_memory_cache[key] = str(int_value)
                logger.debug(f"Cache increment (memory): {key} by {amount} = {int_value}")
                return int_value
            except ValueError:
                logger.error(f"Cannot increment non-integer value for key '{key}': {current_value}")
                return None

    def get_status(self) -> dict:
        """
        Get current cache status.

        Returns:
            Dictionary with status information
        """
        status = {
            'redis_available': self._ensure_connection(),
            'using_fallback': self.using_fallback,
            'fallback_cache_size': len(self.in_memory_cache),
            'fallback_expiring_keys': len(self.in_memory_cache_expiry),
            'redis_url': self.redis_url,
            'last_connection_attempt': self.last_connection_attempt.isoformat() if self.last_connection_attempt else None
        }

        if self.redis_client:
            try:
                # Get Redis info
                redis_info = self.redis_client.info()
                status['redis_memory_used'] = redis_info.get('used_memory_human', 'unknown')
                status['redis_connected_clients'] = redis_info.get('connected_clients', 'unknown')
                status['redis uptime'] = redis_info.get('uptime_in_seconds', 'unknown')
            except Exception as e:
                logger.warning(f"Failed to get Redis info: {e}")

        return status

    def clear_fallback_cache(self):
        """Clear the fallback in-memory cache."""
        with self.cache_lock:
            cleared_count = len(self.in_memory_cache)
            self.in_memory_cache.clear()
            self.in_memory_cache_expiry.clear()
            logger.info(f"Cleared {cleared_count} entries from fallback cache")

    def force_reconnect(self) -> bool:
        """
        Force reconnection attempt to Redis.

        Returns:
            True if reconnection successful
        """
        logger.info("Forcing Redis reconnection...")
        self.redis_client = None
        return self._connect()

    def close(self):
        """Close Redis connection and cleanup resources."""
        if self.redis_client:
            try:
                self.redis_client.close()
                logger.info("Redis connection closed")
            except Exception as e:
                logger.warning(f"Error closing Redis connection: {e}")

        self.clear_fallback_cache()


# Global instance for easy access
_redis_instance: Optional[ResilientRedis] = None


def get_resilient_redis(redis_url: str, timeout: int = 5, max_retries: int = 3) -> ResilientRedis:
    """
    Get or create a resilient Redis instance.

    Args:
        redis_url: Redis connection URL
        timeout: Connection timeout in seconds
        max_retries: Maximum number of connection attempts

    Returns:
        ResilientRedis instance
    """
    global _redis_instance
    if _redis_instance is None:
        _redis_instance = ResilientRedis(redis_url, timeout, max_retries)
    return _redis_instance


def redis_available() -> bool:
    """
    Check if Redis module is available.

    Returns:
        True if redis module is installed
    """
    return REDIS_AVAILABLE