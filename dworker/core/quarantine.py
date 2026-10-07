"""
quarantine 行级隔离
隔离行全量存 quarantine.payload (JSONB) + failed_rules
状态机: pending → replayed / rejected / fixed
"""
import json
import logging
from typing import Optional

import psycopg2

logger = logging.getLogger(__name__)


class QuarantineWriter:
    """Writes blocked rows to the quarantine table."""

    def __init__(self, conn):
        self.conn = conn

    def quarantine_batch(self, job_name: str, target_table: str,
                         blocked_rows: list, source: str) -> int:
        """
        Insert blocked rows into quarantine table.
        Returns number of rows quarantined.
        """
        if not blocked_rows:
            return 0

        count = 0
        with self.conn.cursor() as cur:
            for item in blocked_rows:
                row = item["row"]
                row_key = item.get("row_key", "unknown")
                failed_rules = item.get("failed_rules", [])

                cur.execute("""
                    INSERT INTO quarantine (job, target_table, row_key, payload, failed_rules, source)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    job_name,
                    target_table,
                    row_key,
                    json.dumps(row, default=str),
                    json.dumps(failed_rules),
                    source
                ))
                count += 1

        self.conn.commit()
        logger.info(f"Quarantined {count} rows for {job_name} → {target_table}")
        return count

    def get_pending_count(self, target_table: str = None) -> int:
        with self.conn.cursor() as cur:
            if target_table:
                cur.execute(
                    "SELECT COUNT(*) FROM quarantine WHERE status='pending' AND target_table=%s",
                    (target_table,)
                )
            else:
                cur.execute("SELECT COUNT(*) FROM quarantine WHERE status='pending'")
            return cur.fetchone()[0]
