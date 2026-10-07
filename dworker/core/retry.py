"""
重试执行器
3 次退避重试 5s/30s/120s（可由 job_registry.retry_policy 覆盖）
"""
import logging
import time
from typing import Callable, Any

from .degradation import SourceError, SourceErrorKind

logger = logging.getLogger(__name__)

DEFAULT_RETRY_POLICY = {
    "tries": 3,
    "backoff_s": [5, 30, 120]
}


class RetryExecutor:
    """
    Retry with exponential backoff.
    Only retries on NETWORK and RATE_LIMIT errors.
    SCHEMA_CHANGE and AUTH are not retried.
    """

    def __init__(self, policy: dict = None):
        self.policy = policy or DEFAULT_RETRY_POLICY

    def execute(self, fn: Callable, source_name: str = "") -> Any:
        tries = self.policy.get("tries", 3)
        backoff = self.policy.get("backoff_s", [5, 30, 120])

        last_error = None
        for attempt in range(tries):
            try:
                return fn()
            except SourceError as e:
                last_error = e
                # Don't retry schema change or auth errors
                if e.kind in (SourceErrorKind.SCHEMA_CHANGE, SourceErrorKind.AUTH):
                    raise
                # Don't retry EMPTY
                if e.kind == SourceErrorKind.EMPTY:
                    raise

                if attempt < tries - 1:
                    wait = backoff[min(attempt, len(backoff) - 1)]
                    logger.info(f"[{source_name}] Retry {attempt + 1}/{tries} after {wait}s: {e}")
                    time.sleep(wait)
                else:
                    raise
            except Exception as e:
                last_error = e
                if attempt < tries - 1:
                    wait = backoff[min(attempt, len(backoff) - 1)]
                    logger.info(f"[{source_name}] Retry {attempt + 1}/{tries} after {wait}s: {e}")
                    time.sleep(wait)
                else:
                    raise

        raise last_error
