"""
tests/test_missed_detection.py
漏跑检测测试
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta


class TestMissedDetection:
    """Test missed run detection logic."""

    def test_detect_missed_job(self):
        """Job with no recent runs is detected as missed."""
        # Mock connection and cursor
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        # fetchall returns critical jobs; fetchone returns count=0 for each
        mock_cursor.fetchall.return_value = [
            ("j_index_daily", "10 15 * * 1-5", "D1"),
            ("j_stock_daily", "30 15 * * 1-5", "D2"),
        ]
        mock_cursor.fetchone.return_value = (0,)  # No runs found

        from dsched.main import detect_missed_runs

        missed = detect_missed_runs(mock_conn, lookback_hours=24)

        assert len(missed) == 2
        assert missed[0]["job_name"] == "j_index_daily"
        assert missed[1]["job_name"] == "j_stock_daily"

    def test_no_missed_when_runs_exist(self):
        """Job with recent runs is not flagged."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        mock_cursor.fetchall.return_value = [
            ("j_index_daily", "10 15 * * 1-5", "D1"),
        ]
        mock_cursor.fetchone.return_value = (5,)  # 5 runs found

        from dsched.main import detect_missed_runs

        missed = detect_missed_runs(mock_conn, lookback_hours=24)

        assert len(missed) == 0

    def test_non_critical_jobs_ignored(self):
        """Non-critical jobs are not checked."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        # Only non-critical jobs returned (enabled=true AND critical=true filters them out)
        mock_cursor.fetchall.return_value = []

        from dsched.main import detect_missed_runs

        missed = detect_missed_runs(mock_conn, lookback_hours=24)

        assert len(missed) == 0
