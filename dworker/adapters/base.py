"""
Base adapter interface.
All source adapters implement: fetch(job_ctx, params) -> FetchResult | raise SourceError
And optionally: probe_schema(rows) -> bool
"""
from abc import ABC, abstractmethod
from typing import List

from dworker.core.degradation import JobContext, FetchResult


class BaseAdapter(ABC):
    """Base class for all source adapters."""

    source_name: str = "unknown"

    @abstractmethod
    def fetch(self, job_ctx: JobContext, params: dict) -> FetchResult:
        """
        Fetch data from the source.
        Returns FetchResult with rows list.
        Raises SourceError on failure.
        """
        pass

    def probe_schema(self, rows: list) -> bool:
        """
        Minimal schema assertion on returned data.
        Returns True if schema looks valid.
        Default: check first row has at least one key.
        """
        if not rows:
            return False
        return isinstance(rows[0], dict) and len(rows[0]) > 0
