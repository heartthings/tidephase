"""
tests/test_degradation.py
降级链测试：主源失败→备源成功
"""
import pytest
from unittest.mock import MagicMock

from dworker.core.degradation import (
    DegradationChain, JobContext, FetchResult,
    SourceError, SourceErrorKind
)


class MockAdapter:
    def __init__(self, name, result=None, error=None):
        self.source_name = name
        self._result = result
        self._error = error
        self.call_count = 0

    def fetch(self, job_ctx, params):
        self.call_count += 1
        if self._error:
            raise self._error
        return self._result

    def probe_schema(self, rows):
        return bool(rows)


class TestDegradationChain:
    def setup_method(self):
        self.job_ctx = JobContext(
            job_name="test_job",
            domain="D1",
            target_tables=["index_daily"]
        )

    def test_primary_success(self):
        """Primary source succeeds → returns immediately."""
        primary = MockAdapter("primary", FetchResult("primary", [{"close": 100}]))
        backup = MockAdapter("backup", FetchResult("backup", [{"close": 200}]))

        chain = DegradationChain({"primary": primary, "backup": backup})
        result = chain.execute(self.job_ctx, ["primary", "backup"])

        assert result.success is True
        assert result.source_used == "primary"
        assert len(result.rows) == 1
        assert primary.call_count == 1
        assert backup.call_count == 0

    def test_primary_fails_backup_succeeds(self):
        """Primary fails → fallback to backup."""
        primary = MockAdapter("primary",
                              error=SourceError(SourceErrorKind.NETWORK, "timeout", "primary"))
        backup = MockAdapter("backup", FetchResult("backup", [{"close": 200}]))

        chain = DegradationChain({"primary": primary, "backup": backup})
        result = chain.execute(self.job_ctx, ["primary", "backup"])

        assert result.success is True
        assert result.source_used == "backup"
        assert len(result.rows) == 1
        assert primary.call_count == 1
        assert backup.call_count == 1

    def test_all_fail_returns_miss(self):
        """All sources fail → MISS."""
        primary = MockAdapter("primary",
                              error=SourceError(SourceErrorKind.NETWORK, "timeout", "primary"))
        backup = MockAdapter("backup",
                             error=SourceError(SourceErrorKind.EMPTY, "no data", "backup"))

        chain = DegradationChain({"primary": primary, "backup": backup})
        result = chain.execute(self.job_ctx, ["primary", "backup"])

        assert result.success is False
        assert result.source_used is None
        assert len(result.rows) == 0
        assert len(result.fallback_log) == 2

    def test_empty_result_triggers_fallback(self):
        """Primary returns empty → fallback to backup."""
        primary = MockAdapter("primary",
                              error=SourceError(SourceErrorKind.EMPTY, "empty", "primary"))
        backup = MockAdapter("backup", FetchResult("backup", [{"close": 300}]))

        chain = DegradationChain({"primary": primary, "backup": backup})
        result = chain.execute(self.job_ctx, ["primary", "backup"])

        assert result.success is True
        assert result.source_used == "backup"

    def test_missing_adapter_skipped(self):
        """Adapter not registered → skipped, try next."""
        backup = MockAdapter("backup", FetchResult("backup", [{"close": 400}]))

        chain = DegradationChain({"backup": backup})
        result = chain.execute(self.job_ctx, ["nonexistent", "backup"])

        assert result.success is True
        assert result.source_used == "backup"
        assert len(result.fallback_log) == 1
        assert "NOT_FOUND" in result.fallback_log[0][1]

    def test_schema_probe_failure_triggers_fallback(self):
        """Schema probe fails → fallback."""
        primary = MockAdapter("primary", FetchResult("primary", [{"bad": "data"}]))
        primary.probe_schema = lambda rows: False  # Always fails
        backup = MockAdapter("backup", FetchResult("backup", [{"close": 500}]))

        chain = DegradationChain({"primary": primary, "backup": backup})
        result = chain.execute(self.job_ctx, ["primary", "backup"])

        assert result.success is True
        assert result.source_used == "backup"
