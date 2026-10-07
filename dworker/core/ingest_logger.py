"""
ingest_log 写入器
每作业每 run 一行。
"""
import logging
import time

logger = logging.getLogger(__name__)


class IngestLogger:
    """Writes one row per job run to ingest_log."""

    def __init__(self, conn):
        self.conn = conn

    def log_run(self, job_name: str, domain: str, target_table: str,
                source_used: str, status: str,
                rows_in: int = 0, rows_written: int = 0,
                rows_quarantined: int = 0, verify_diff_max: float = None,
                duration_ms: int = None, note: str = None,
                trigger: str = "scheduled") -> int:
        """
        Write one ingest_log row. Returns run_id.
        status: OK / PARTIAL / FAIL / MISS
        """
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO ingest_log
                    (job, trigger, domain, target_table, source_used, status,
                     rows_in, rows_written, rows_quarantined, verify_diff_max,
                     duration_ms, note)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING run_id
            """, (
                job_name, trigger, domain, target_table, source_used, status,
                rows_in, rows_written, rows_quarantined, verify_diff_max,
                duration_ms, note
            ))
            run_id = cur.fetchone()[0]
        self.conn.commit()
        logger.info(f"ingest_log: {job_name} status={status} rows={rows_written} run_id={run_id}")
        return run_id
