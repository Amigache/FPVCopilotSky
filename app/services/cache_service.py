"""
Centralized Caching Service

Provides a unified caching mechanism with TTL (Time To Live) support,
invalidation, and pattern-based cache clearing.

Features:
- TTL-based expiration
- Manual invalidation
- Pattern-based invalidation (regex)
- Thread-safe operations
- Memory-efficient storage

Usage:
    from app.services.cache_service import get_cache_service

    cache = get_cache_service()

    # Set with TTL
    cache.set("network_status", data, ttl=2)

    # Get (returns None if expired or not found)
    data = cache.get("network_status")

    # Invalidate specific key
    cache.invalidate("network_status")

    # Invalidate by pattern
    cache.invalidate_pattern("network_.*")
"""

import time
import re
import threading
from typing import Any, Optional, Dict
from app.utils.logger import get_logger

logger = get_logger(__name__)


class CacheService:
    """Centralized caching with TTL and invalidation support"""

    def __init__(self):
        """Initialize cache service with thread lock"""
        self._caches: Dict[str, Dict[str, Any]] = {}
        self._ttls: Dict[str, float] = {}
        self._lock = threading.RLock()
        logger.info("Cache service initialized")

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get cached value if not expired

        Args:
            key: Cache key
            default: Default value if not found or expired

        Returns:
            Cached value or default
        """
        with self._lock:
            if key not in self._caches:
                return default

            cache_entry = self._caches[key]
            ttl = self._ttls.get(key, 0)

            # Check expiration
            if ttl > 0:
                age = time.time() - cache_entry["timestamp"]
                if age > ttl:
                    # Expired - remove and return default
                    del self._caches[key]
                    if key in self._ttls:
                        del self._ttls[key]
                    logger.debug(f"Cache expired: {key} (age: {age:.1f}s, ttl: {ttl}s)")
                    return default

            return cache_entry["data"]

    def set(self, key: str, value: Any, ttl: float = 0) -> None:
        """
        Set cached value with optional TTL

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds (0 = no expiration)
        """
        with self._lock:
            self._caches[key] = {"data": value, "timestamp": time.time()}

            if ttl > 0:
                self._ttls[key] = ttl
            elif key in self._ttls:
                # Remove TTL if set to 0
                del self._ttls[key]

            logger.debug(f"Cache set: {key} (ttl: {ttl}s)")

    def invalidate(self, key: str) -> bool:
        """
        Invalidate (remove) specific cache entry

        Args:
            key: Cache key to invalidate

        Returns:
            True if cache was found and removed, False otherwise
        """
        with self._lock:
            if key in self._caches:
                del self._caches[key]
                if key in self._ttls:
                    del self._ttls[key]
                logger.debug(f"Cache invalidated: {key}")
                return True
            return False

    def invalidate_pattern(self, pattern: str) -> int:
        """
        Invalidate all caches matching regex pattern

        Args:
            pattern: Regex pattern to match cache keys

        Returns:
            Number of caches invalidated
        """
        with self._lock:
            try:
                regex = re.compile(pattern)
                keys_to_delete = [k for k in self._caches.keys() if regex.match(k)]

                for key in keys_to_delete:
                    del self._caches[key]
                    if key in self._ttls:
                        del self._ttls[key]

                if keys_to_delete:
                    logger.debug(f"Cache pattern invalidated: {pattern} ({len(keys_to_delete)} entries)")

                return len(keys_to_delete)
            except re.error as e:
                logger.error(f"Invalid regex pattern '{pattern}': {e}")
                return 0

    def clear_all(self) -> int:
        """
        Clear all cached entries

        Returns:
            Number of entries cleared
        """
        with self._lock:
            count = len(self._caches)
            self._caches.clear()
            self._ttls.clear()
            logger.info(f"Cache cleared: {count} entries removed")
            return count

    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics

        Returns:
            Dictionary with cache stats
        """
        with self._lock:
            now = time.time()
            expired_count = 0

            # Count expired entries
            for key, cache_entry in self._caches.items():
                ttl = self._ttls.get(key, 0)
                if ttl > 0:
                    age = now - cache_entry["timestamp"]
                    if age > ttl:
                        expired_count += 1

            return {
                "total_entries": len(self._caches),
                "entries_with_ttl": len(self._ttls),
                "expired_entries": expired_count,
                "active_entries": len(self._caches) - expired_count,
            }

    def has_key(self, key: str) -> bool:
        """
        Check if key exists in cache (regardless of expiration)

        Args:
            key: Cache key to check

        Returns:
            True if key exists, False otherwise
        """
        with self._lock:
            return key in self._caches

    def get_age(self, key: str) -> Optional[float]:
        """
        Get age of cached entry in seconds

        Args:
            key: Cache key

        Returns:
            Age in seconds or None if not found
        """
        with self._lock:
            if key not in self._caches:
                return None

            cache_entry = self._caches[key]
            return time.time() - cache_entry["timestamp"]


# Singleton instance
_cache_service_instance: Optional[CacheService] = None
_cache_service_lock = threading.Lock()


def get_cache_service() -> CacheService:
    """
    Get singleton cache service instance

    Returns:
        CacheService instance
    """
    global _cache_service_instance

    if _cache_service_instance is None:
        with _cache_service_lock:
            if _cache_service_instance is None:
                _cache_service_instance = CacheService()

    return _cache_service_instance


def clear_cache_service():
    """Clear the singleton cache service instance (useful for testing)"""
    global _cache_service_instance

    with _cache_service_lock:
        if _cache_service_instance is not None:
            _cache_service_instance.clear_all()
            _cache_service_instance = None
