"""
降级链执行器
按 job_registry.source_chain 逐源尝试，行级 source 标记。
全败写 ingest_log MISS + critical 告警钩子。
"""
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class SourceErrorKind(Enum):
    NETWORK = "NETWORK"
    RATE_LIMIT = "RATE_LIMIT"
    SCHEMA_CHANGE = "SCHEMA_CHANGE"
    EMPTY = "EMPTY"
    AUTH = "AUTH"


class SourceError(Exception):
    def __init__(self, kind: SourceErrorKind, message: str, source: str = ""):
        self.kind = kind
        self.source = source
        super().__init__(f"[{kind.value}] {source}: {message}")


@dataclass
class JobContext:
    job_name: str
    domain: str
    target_tables: list
    params: dict = field(default_factory=dict)
    run_id: Optional[int] = None


@dataclass
class FetchResult:
    source: str
    rows: list
    raw_payload: Optional[Any] = None


@dataclass
class DegradationResult:
    success: bool
    source_used: Optional[str] = None
    rows: list = field(default_factory=list)
    raw_payload: Optional[Any] = None
    fallback_log: list = field(default_factory=list)  # [(source, error_kind, message)]


class DegradationChain:
    """
    降级链执行器。
    按 source_chain 顺序逐源尝试 fetch，成功则返回。
    全部失败则返回 MISS。
    """

    def __init__(self, adapters: dict, rate_limiter=None, retry_executor=None):
        """
        adapters: {source_name: adapter_instance}
        adapter_instance.fetch(job_ctx, params) -> FetchResult | raise SourceError
        """
        self.adapters = adapters
        self.rate_limiter = rate_limiter
        self.retry_executor = retry_executor

    def execute(self, job_ctx: JobContext, source_chain: list, params: dict = None) -> DegradationResult:
        params = params or {}
        fallback_log = []

        for source_name in source_chain:
            adapter = self.adapters.get(source_name)
            if adapter is None:
                fallback_log.append((source_name, "NOT_FOUND", f"Adapter {source_name} not registered"))
                logger.warning(f"[{job_ctx.job_name}] Adapter {source_name} not registered, skipping")
                continue

            # Rate limit
            if self.rate_limiter:
                self.rate_limiter.acquire(source_name)

            # Fetch with retry
            try:
                if self.retry_executor:
                    result = self.retry_executor.execute(
                        lambda: adapter.fetch(job_ctx, params),
                        source_name=source_name
                    )
                else:
                    result = adapter.fetch(job_ctx, params)

                if result and result.rows:
                    # Schema probe
                    if hasattr(adapter, 'probe_schema') and not adapter.probe_schema(result.rows):
                        raise SourceError(SourceErrorKind.SCHEMA_CHANGE,
                                          "Schema probe failed", source_name)

                    logger.info(f"[{job_ctx.job_name}] Success from {source_name}: {len(result.rows)} rows")
                    return DegradationResult(
                        success=True,
                        source_used=source_name,
                        rows=result.rows,
                        raw_payload=result.raw_payload,
                        fallback_log=fallback_log
                    )
                else:
                    raise SourceError(SourceErrorKind.EMPTY, "No rows returned", source_name)

            except SourceError as e:
                fallback_log.append((source_name, e.kind.value, str(e)))
                logger.warning(f"[{job_ctx.job_name}] Source {source_name} failed: {e}")
                continue
            except Exception as e:
                fallback_log.append((source_name, "UNKNOWN", str(e)))
                logger.error(f"[{job_ctx.job_name}] Source {source_name} unexpected error: {e}")
                continue

        # All sources failed
        logger.error(f"[{job_ctx.job_name}] ALL sources failed. Fallback log: {fallback_log}")
        return DegradationResult(
            success=False,
            fallback_log=fallback_log
        )
