"""
限速令牌桶
configs/rate_limits.yaml 驱动。
"""
import threading
import time
import yaml
from pathlib import Path
from typing import Optional


DEFAULT_RATE_LIMITS = {
    "eastmoney": {"rps": 0.5, "burst": 2},
    "tencent": {"rps": 2.0, "burst": 4},
    "akshare": {"rps": 1.0, "burst": 1, "jitter_s": [0.3, 1.0]},
    "mootdx": {"rps": 4.0, "burst": 4},
    "sina": {"rps": 2.0, "burst": 4},
    "longhu": {"rps": 0.5, "burst": 1},
    "hkex": {"rps": 0.5, "burst": 2},
    "cninfo": {"rps": 0.5, "burst": 2},
    "cls": {"rps": 0.5, "burst": 2},
    "ths": {"rps": 0.5, "burst": 2},
    "internal": {"rps": 10.0, "burst": 10},
}


class TokenBucket:
    """Simple token bucket rate limiter."""

    def __init__(self, rate: float, burst: int, jitter: Optional[list] = None):
        self.rate = rate           # tokens per second
        self.burst = burst         # max tokens
        self.jitter = jitter       # [min_s, max_s] random jitter after acquire
        self.tokens = float(burst)
        self.last_refill = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self):
        with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_refill
            self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
            self.last_refill = now

            if self.tokens < 1.0:
                wait_time = (1.0 - self.tokens) / self.rate
                time.sleep(wait_time)
                self.tokens = 0.0
            else:
                self.tokens -= 1.0

        # Jitter
        if self.jitter:
            import random
            jitter_s = random.uniform(self.jitter[0], self.jitter[1])
            time.sleep(jitter_s)


class RateLimiter:
    """
    Global rate limiter manager.
    Loads from configs/rate_limits.yaml, falls back to defaults.
    """

    def __init__(self, config_path: Optional[str] = None):
        self.buckets = {}
        config = self._load_config(config_path)

        for source, params in config.items():
            rps = params.get("rps", 1.0)
            burst = params.get("burst", 1)
            jitter = params.get("jitter_s")
            self.buckets[source] = TokenBucket(rps, burst, jitter)

    def _load_config(self, config_path: Optional[str]) -> dict:
        if config_path and Path(config_path).exists():
            with open(config_path) as f:
                return yaml.safe_load(f) or DEFAULT_RATE_LIMITS
        return DEFAULT_RATE_LIMITS

    def acquire(self, source: str):
        bucket = self.buckets.get(source)
        if bucket:
            bucket.acquire()
        # If source not configured, no rate limiting (pass through)
