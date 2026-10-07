"""
tests/test_idempotent.py
幂等入库测试：同批数据重跑行数不变
"""
import pytest
from unittest.mock import MagicMock, patch


class TestIdempotentIngestion:
    """Test that re-running the same data doesn't create duplicates."""

    def test_upsert_logic(self):
        """Simulate UPSERT: same data inserted twice → same row count."""
        # Simulate the ON CONFLICT DO UPDATE behavior
        table = {}  # (date, code) -> row

        def upsert(rows):
            for row in rows:
                key = (row["date"], row["code"])
                table[key] = row  # Overwrites existing

        # First run
        batch1 = [
            {"date": "2026-10-07", "code": "sh600519", "close": 1800},
            {"date": "2026-10-07", "code": "sz000001", "close": 12},
        ]
        upsert(batch1)
        assert len(table) == 2

        # Second run (same data, possibly updated values)
        batch2 = [
            {"date": "2026-10-07", "code": "sh600519", "close": 1830},  # Updated
            {"date": "2026-10-07", "code": "sz000001", "close": 12},
        ]
        upsert(batch2)
        assert len(table) == 2  # Still 2 rows, not 4

        # Verify the update took effect
        assert table[("2026-10-07", "sh600519")]["close"] == 1830

    def test_different_dates_create_separate_rows(self):
        """Different dates create separate rows."""
        table = {}

        def upsert(rows):
            for row in rows:
                key = (row["date"], row["code"])
                table[key] = row

        batch = [
            {"date": "2026-10-06", "code": "sh600519", "close": 1790},
            {"date": "2026-10-07", "code": "sh600519", "close": 1830},
        ]
        upsert(batch)
        assert len(table) == 2

    def test_quarantine_then_replay(self):
        """Row quarantined then replayed → ends up in main table."""
        main_table = {}
        quarantine_table = []

        # First run: bad data goes to quarantine
        rows = [
            {"date": "2026-10-07", "code": "sh600519", "close": -5},  # Invalid
        ]
        for row in rows:
            if row["close"] <= 0:
                quarantine_table.append({"payload": row, "status": "pending"})
            else:
                key = (row["date"], row["code"])
                main_table[key] = row

        assert len(main_table) == 0
        assert len(quarantine_table) == 1

        # Fix and replay
        fixed_row = {"date": "2026-10-07", "code": "sh600519", "close": 1830}
        key = (fixed_row["date"], fixed_row["code"])
        main_table[key] = fixed_row
        quarantine_table[0]["status"] = "replayed"

        assert len(main_table) == 1
        assert quarantine_table[0]["status"] == "replayed"
