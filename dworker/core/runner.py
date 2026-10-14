"""
作业执行器
统一调度 → 降级链 → handler → 写库 → ingest_log → raw 归档
"""
import importlib
import json
import logging
import os
import time
import traceback
from datetime import datetime
from pathlib import Path

import psycopg2

from dworker.core.degradation import (
    DegradationChain, JobContext, SourceError, SourceErrorKind
)
from dworker.core.ingest_logger import IngestLogger
from dworker.core.raw_archive import RawArchiver
from dworker.core.retry import RetryExecutor
from dworker.core.rate_limiter import RateLimiter
from dworker.core.quarantine import QuarantineWriter

logger = logging.getLogger(__name__)

# Adapter registry
ADAPTER_CLASSES = {}

def _load_adapters():
    global ADAPTER_CLASSES
    if ADAPTER_CLASSES:
        return
    from dworker.adapters.tencent import TencentAdapter
    from dworker.adapters.akshare import AkshareAdapter
    from dworker.adapters.mootdx import MootdxAdapter
    from dworker.adapters.eastmoney import EastmoneyAdapter
    from dworker.adapters.sina import SinaAdapter
    ADAPTER_CLASSES = {
        "tencent": TencentAdapter,
        "akshare": AkshareAdapter,
        "mootdx": MootdxAdapter,
        "eastmoney": EastmoneyAdapter,
        "sina": SinaAdapter,
    }


def build_adapters() -> dict:
    _load_adapters()
    instances = {}
    for name, cls in ADAPTER_CLASSES.items():
        try:
            instances[name] = cls()
        except Exception as e:
            logger.warning(f"Failed to init adapter {name}: {e}")
    return instances


def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("MARKET_TSDB_HOST", "127.0.0.1"),
        port=int(os.getenv("MARKET_TSDB_PORT", "15432")),
        dbname=os.getenv("MARKET_TSDB_NAME", "market_tsdb"),
        user=os.getenv("MARKET_TSDB_USER", "duser_writer"),
        password=os.getenv("MARKET_TSDB_PASSWORD", ""),
    )


def load_job_config(conn, job_name: str) -> dict:
    """Load job config from job_registry."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT job_name, domain, target_tables, schedule_cron,
                   source_chain, retry_policy, timeout_s, critical, enabled, note
            FROM job_registry WHERE job_name = %s
        """, (job_name,))
        row = cur.fetchone()
    if not row:
        return None
    return {
        "job_name": row[0],
        "domain": row[1],
        "target_tables": row[2],
        "schedule_cron": row[3],
        "source_chain": row[4] if isinstance(row[4], list) else json.loads(row[4] or "[]"),
        "retry_policy": row[5] if isinstance(row[5], dict) else json.loads(row[5] or '{"tries":3,"backoff_s":[5,30,120]}'),
        "timeout_s": row[6],
        "critical": row[7],
        "enabled": row[8],
        "note": row[9],
    }


def load_handler(job_name: str):
    """Dynamically load handler module from dworker/jobs/{job_name}.py"""
    handler_path = Path(__file__).resolve().parent.parent / "jobs" / f"{job_name}.py"
    if not handler_path.exists():
        logger.error(f"Handler not found: {handler_path}")
        return None
    try:
        mod = importlib.import_module(f"dworker.jobs.{job_name}")
        return importlib.reload(mod)
    except Exception as e:
        logger.error(f"Failed to load handler {job_name}: {e}")
        return None


def execute_job(job_name: str, trigger: str = "scheduled",
                extra_params: dict = None, conn=None):
    """
    Execute a single job end-to-end.
    Returns (success: bool, note: str).
    """
    t0 = time.time()
    own_conn = conn is None
    if own_conn:
        conn = get_db_connection()

    ingest = IngestLogger(conn)
    archiver = RawArchiver(base_dir="/app/data/raw" if Path("/app/data/raw").exists() else "data/raw")

    try:
        # Load job config
        job_cfg = load_job_config(conn, job_name)
        if not job_cfg:
            logger.error(f"[{job_name}] Not found in job_registry")
            return False, "job not in registry"

        if not job_cfg["enabled"]:
            logger.info(f"[{job_name}] Disabled, skipping")
            return True, "disabled"

        # Load handler
        handler_mod = load_handler(job_name)
        if handler_mod is None:
            ingest.log_run(
                job_name=job_name, domain=job_cfg["domain"],
                target_table=",".join(job_cfg["target_tables"]),
                source_used="none", status="FAIL",
                duration_ms=int((time.time() - t0) * 1000),
                note="handler not implemented", trigger=trigger,
            )
            return False, "handler not found"

        # Build degradation chain
        adapters = build_adapters()
        retry_exec = RetryExecutor(policy=job_cfg["retry_policy"])
        rate_limiter = RateLimiter()
        deg_chain = DegradationChain(adapters, rate_limiter, retry_exec)

        # Build job context
        job_ctx = JobContext(
            job_name=job_name,
            domain=job_cfg["domain"],
            target_tables=job_cfg["target_tables"],
            params=extra_params or {},
        )

        # Execute handler
        logger.info(f"[{job_name}] Starting execution (trigger={trigger})")
        result = handler_mod.run(
            job_ctx=job_ctx,
            deg_chain=deg_chain,
            source_chain=job_cfg["source_chain"],
            conn=conn,
            ingest_logger=ingest,
            raw_archiver=archiver,
            trigger=trigger,
        )

        duration_ms = int((time.time() - t0) * 1000)
        success = result.get("success", False)
        status = "OK" if success else ("PARTIAL" if result.get("rows_written", 0) > 0 else "FAIL")

        # Log to ingest_log (handler may have already logged; this is the summary)
        if not result.get("already_logged"):
            ingest.log_run(
                job_name=job_name,
                domain=job_cfg["domain"],
                target_table=",".join(job_cfg["target_tables"]),
                source_used=result.get("source_used", "unknown"),
                status=status,
                rows_in=result.get("rows_in", 0),
                rows_written=result.get("rows_written", 0),
                rows_quarantined=result.get("rows_quarantined", 0),
                duration_ms=duration_ms,
                note=result.get("note", ""),
                trigger=trigger,
            )

        logger.info(f"[{job_name}] Done: {status} rows={result.get('rows_written', 0)} "
                     f"src={result.get('source_used', '?')} {duration_ms}ms")
        return success, result.get("note", status)

    except Exception as e:
        duration_ms = int((time.time() - t0) * 1000)
        tb = traceback.format_exc()
        logger.error(f"[{job_name}] EXCEPTION: {e}\n{tb}")
        try:
            ingest.log_run(
                job_name=job_name, domain="unknown",
                target_table="", source_used="none", status="FAIL",
                duration_ms=duration_ms, note=f"EXCEPTION: {str(e)[:200]}",
                trigger=trigger,
            )
        except Exception:
            pass
        return False, str(e)
    finally:
        if own_conn:
            try:
                conn.close()
            except Exception:
                pass
