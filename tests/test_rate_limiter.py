"""
tests/test_rate_limiter.py
限速令牌桶测试
"""
import pytest
import time

from dworker.core.rate_limiter import TokenBucket, RateLimiter


class TestTokenBucket:
    def test_basic_acquire(self):
        """Token bucket allows acquire within burst."""
        bucket = TokenBucket(rate=10, burst=5)
        start = time.monotonic()
        for _ in range(5):
            bucket.acquire()
        elapsed = time.monotonic() - start
        # Should complete quickly (within burst)
        assert elapsed < 1.0

    def test_rate_limiting(self):
        """Token bucket enforces rate limit."""
        bucket = TokenBucket(rate=2, burst=1)  # 2 rps, burst 1
        # First acquire uses the burst token
        bucket.acquire()
        # Second acquire should wait ~0.5s
        start = time.monotonic()
        bucket.acquire()
        elapsed = time.monotonic() - start
        assert elapsed >= 0.3  # Allow some tolerance

    def test_burst_capacity(self):
        """Burst allows multiple immediate acquires."""
        bucket = TokenBucket(rate=1, burst=3)
        start = time.monotonic()
        for _ in range(3):
            bucket.acquire()
        elapsed = time.monotonic() - start
        assert elapsed < 0.5  # All 3 should be immediate


class TestRateLimiter:
    def test_default_config(self):
        """RateLimiter loads default config."""
        limiter = RateLimiter()
        assert "eastmoney" in limiter.buckets
        assert "tencent" in limiter.buckets
        assert "akshare" in limiter.buckets

    def test_acquire_known_source(self):
        """Acquire for known source works."""
        limiter = RateLimiter()
        limiter.acquire("internal")  # Should not block (high rate)

    def test_acquire_unknown_source(self):
        """Acquire for unknown source passes through."""
        limiter = RateLimiter()
        limiter.acquire("unknown_source")  # Should not raise
