"""
Business Reporting Dashboard — Rate Limiting Service (Milestone 5)

Supports:
- Redis-backed sliding-window rate limiting for distributed deployments.
- In-memory sliding-window fallback when Redis is unconfigured or unavailable.
"""

from __future__ import annotations

import collections
import logging
import os
import threading
import time
from typing import Optional

logger = logging.getLogger("rate_limiter")


class RateLimiter:
    """Sliding-window rate limiter with Redis backend and in-memory fallback."""

    def __init__(self):
        self._memory_store = collections.defaultdict(list)
        self._lock = threading.Lock()
        self._redis_client = None
        self._redis_checked = False

    def _get_redis(self):
        if self._redis_checked:
            return self._redis_client

        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        try:
            import redis
            client = redis.from_url(redis_url, socket_connect_timeout=0.5, socket_timeout=0.5)
            client.ping()
            self._redis_client = client
            logger.info("RateLimiter connected to Redis.")
        except Exception:
            self._redis_client = None
            logger.info("RateLimiter using in-memory sliding-window storage.")

        self._redis_checked = True
        return self._redis_client

    def is_rate_limited(
        self,
        key: str,
        max_requests: int,
        window_seconds: int,
    ) -> bool:
        """
        Check if the key has exceeded max_requests in the window_seconds.
        Records the current request timestamp if allowed.
        Returns True if rate limited (exceeded), False if allowed.
        """
        now = time.time()
        client = self._get_redis()

        if client is not None:
            try:
                redis_key = f"rate_limit:{key}"
                pipe = client.pipeline()
                # Remove timestamps older than window
                pipe.zremrangebyscore(redis_key, 0, now - window_seconds)
                # Count remaining timestamps
                pipe.zcard(redis_key)
                # Add current timestamp
                pipe.zadd(redis_key, {str(now): now})
                # Expire key after window
                pipe.expire(redis_key, window_seconds + 5)
                results = pipe.execute()

                current_count = results[1]
                if current_count >= max_requests:
                    return True
                return False
            except Exception as exc:
                logger.warning(f"Redis rate limit check failed, falling back to memory: {exc}")

        # In-memory sliding window fallback
        with self._lock:
            cutoff = now - window_seconds
            timestamps = self._memory_store[key]
            # Prune old timestamps
            self._memory_store[key] = [t for t in timestamps if t > cutoff]

            if len(self._memory_store[key]) >= max_requests:
                return True

            self._memory_store[key].append(now)
            return False

    def reset(self, key: Optional[str] = None):
        """Reset rate limits (useful for testing)."""
        with self._lock:
            if key:
                self._memory_store.pop(key, None)
            else:
                self._memory_store.clear()
        client = self._get_redis()
        if client is not None:
            try:
                if key:
                    client.delete(f"rate_limit:{key}")
                else:
                    r_keys = client.keys("rate_limit:*")
                    if r_keys:
                        client.delete(*r_keys)
            except Exception:
                pass


# Global singleton rate limiter
rate_limiter = RateLimiter()
