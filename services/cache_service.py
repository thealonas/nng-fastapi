"""
Cache service module - provides in-memory caching with TTL support.
"""

import datetime
import threading
from typing import Optional, Dict, Any, Callable, TypeVar, Generic
from dataclasses import dataclass
from enum import Enum


T = TypeVar("T")


class CachePolicy(str, Enum):
    LRU = "lru"
    LFU = "lfu"
    FIFO = "fifo"


@dataclass
class CacheEntry(Generic[T]):
    value: T
    created_at: datetime.datetime
    expires_at: Optional[datetime.datetime]
    access_count: int = 0
    last_accessed: datetime.datetime = None

    def __post_init__(self):
        if self.last_accessed is None:
            self.last_accessed = self.created_at

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.datetime.now() > self.expires_at

    def touch(self) -> None:
        self.access_count += 1
        self.last_accessed = datetime.datetime.now()


class CacheService:
    def __init__(
        self,
        max_size: int = 1000,
        default_ttl: int = 300,
        policy: CachePolicy = CachePolicy.LRU,
    ):
        self._cache: Dict[str, CacheEntry] = {}
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._policy = policy
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0

    def _make_key(self, namespace: str, key: str) -> str:
        return f"{namespace}:{key}"

    def _evict_if_needed(self) -> None:
        while len(self._cache) >= self._max_size:
            if not self._cache:
                break

            if self._policy == CachePolicy.LRU:
                oldest_key = min(
                    self._cache.keys(), key=lambda k: self._cache[k].last_accessed
                )
            elif self._policy == CachePolicy.LFU:
                oldest_key = min(
                    self._cache.keys(), key=lambda k: self._cache[k].access_count
                )
            else:
                oldest_key = min(
                    self._cache.keys(), key=lambda k: self._cache[k].created_at
                )

            del self._cache[oldest_key]

    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        namespace: str = "default",
    ) -> None:
        with self._lock:
            full_key = self._make_key(namespace, key)

            self._evict_if_needed()

            now = datetime.datetime.now()
            ttl_seconds = ttl if ttl is not None else self._default_ttl
            expires_at = (
                now + datetime.timedelta(seconds=ttl_seconds)
                if ttl_seconds > 0
                else None
            )

            self._cache[full_key] = CacheEntry(
                value=value, created_at=now, expires_at=expires_at
            )

    def get(self, key: str, namespace: str = "default", default: Any = None) -> Any:
        with self._lock:
            full_key = self._make_key(namespace, key)
            entry = self._cache.get(full_key)

            if entry is None:
                self._misses += 1
                return default

            if entry.is_expired():
                del self._cache[full_key]
                self._misses += 1
                return default

            entry.touch()
            self._hits += 1
            return entry.value

    def delete(self, key: str, namespace: str = "default") -> bool:
        with self._lock:
            full_key = self._make_key(namespace, key)
            if full_key in self._cache:
                del self._cache[full_key]
                return True
            return False

    def exists(self, key: str, namespace: str = "default") -> bool:
        with self._lock:
            full_key = self._make_key(namespace, key)
            entry = self._cache.get(full_key)

            if entry is None:
                return False

            if entry.is_expired():
                del self._cache[full_key]
                return False

            return True

    def clear(self, namespace: Optional[str] = None) -> int:
        with self._lock:
            if namespace is None:
                count = len(self._cache)
                self._cache.clear()
                return count

            prefix = f"{namespace}:"
            keys_to_delete = [k for k in self._cache.keys() if k.startswith(prefix)]
            for key in keys_to_delete:
                del self._cache[key]
            return len(keys_to_delete)

    def get_or_set(
        self,
        key: str,
        factory: Callable[[], T],
        ttl: Optional[int] = None,
        namespace: str = "default",
    ) -> T:
        value = self.get(key, namespace)
        if value is not None:
            return value

        value = factory()
        self.set(key, value, ttl, namespace)
        return value

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            total = self._hits + self._misses
            hit_rate = (self._hits / total * 100) if total > 0 else 0.0

            return {
                "size": len(self._cache),
                "max_size": self._max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": hit_rate,
                "policy": self._policy.value,
            }

    def cleanup_expired(self) -> int:
        with self._lock:
            expired_keys = [k for k, v in self._cache.items() if v.is_expired()]
            for key in expired_keys:
                del self._cache[key]
            return len(expired_keys)

    def keys(self, namespace: str = "default") -> list:
        with self._lock:
            prefix = f"{namespace}:"
            return [
                k[len(prefix) :]
                for k in self._cache.keys()
                if k.startswith(prefix) and not self._cache[k].is_expired()
            ]

    def ttl(self, key: str, namespace: str = "default") -> Optional[int]:
        with self._lock:
            full_key = self._make_key(namespace, key)
            entry = self._cache.get(full_key)

            if entry is None or entry.is_expired():
                return None

            if entry.expires_at is None:
                return -1

            remaining = (entry.expires_at - datetime.datetime.now()).total_seconds()
            return max(0, int(remaining))


cache_instance = CacheService()


def cached(
    ttl: int = 300, namespace: str = "default", key_builder: Callable[..., str] = None
):
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        def wrapper(*args, **kwargs):
            if key_builder:
                cache_key = key_builder(*args, **kwargs)
            else:
                cache_key = (
                    f"{func.__name__}:{hash((args, tuple(sorted(kwargs.items()))))}"
                )

            cached_value = cache_instance.get(cache_key, namespace)
            if cached_value is not None:
                return cached_value

            result = func(*args, **kwargs)
            cache_instance.set(cache_key, result, ttl, namespace)
            return result

        return wrapper

    return decorator
