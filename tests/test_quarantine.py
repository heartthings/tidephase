"""
tests/test_quarantine.py
Quarantine 测试：脏行隔离 + pending 状态
"""
import pytest
from unittest.mock import MagicMock, patch

from dworker.validate import ValidationEngine, RuleSeverity


class TestValidationEngine:
    def setup_method(self):
        self.engine = ValidationEngine()

    def test_valid_row_passes(self):
        """Valid row passes all rules."""
        row = {
            "date": "2026-10-07",
            "code": "sh600519",
            "open": 1800.0,
            "high": 1850.0,
            "low": 1790.0,
            "close": 1830.0,
            "volume": 50000,
            "amount": 9e9,
        }
        result = self.engine.validate_row(row)
        assert result.passed is True
        assert len(result.violations) == 0

    def test_ohlc_inconsistency_blocked(self):
        """high < close → blocked."""
        row = {
            "open": 100.0,
            "high": 90.0,  # Less than close!
            "low": 80.0,
            "close": 95.0,
            "volume": 1000,
        }
        result = self.engine.validate_row(row)
        assert result.passed is False
        blocks = [v for v in result.violations if v.severity == RuleSeverity.BLOCK]
        assert len(blocks) > 0
        assert any("ohlc_consistency" in v.rule_name for v in blocks)

    def test_magnitude_out_of_range_blocked(self):
        """close <= 0 → blocked."""
        row = {
            "open": 100.0,
            "high": 110.0,
            "low": 0.0,  # Invalid!
            "close": -5.0,  # Invalid!
            "volume": 1000,
        }
        result = self.engine.validate_row(row)
        assert result.passed is False

    def test_null_close_blocked(self):
        """close is None → blocked."""
        row = {
            "open": 100.0,
            "high": 110.0,
            "low": 90.0,
            "close": None,
        }
        result = self.engine.validate_row(row)
        assert result.passed is False

    def test_high_turnover_warned(self):
        """turnover_rate > 100% → warn but pass."""
        row = {
            "open": 100.0,
            "high": 110.0,
            "low": 90.0,
            "close": 105.0,
            "volume": 1000,
            "amount": 1e6,
            "turnover_rate": 150.0,  # > 100%
        }
        result = self.engine.validate_row(row)
        assert result.passed is True
        assert len(result.warnings) > 0

    def test_batch_validation(self):
        """Batch: some pass, some blocked."""
        rows = [
            {"open": 100, "high": 110, "low": 90, "close": 105, "volume": 1000},  # OK
            {"open": 100, "high": 90, "low": 80, "close": 95, "volume": 1000},   # BAD (high < close)
            {"open": 200, "high": 210, "low": 190, "close": 205, "volume": 2000}, # OK
        ]
        passed, blocked, warned = self.engine.validate_batch(rows)
        assert len(passed) == 2
        assert len(blocked) == 1
        assert blocked[0]["row"]["close"] == 95
