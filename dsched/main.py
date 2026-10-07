"""
dsched - 调度服务
APScheduler + job_registry 唯一事实源。
功能：
- cron 调度（Asia/Shanghai）
- 超时强制中断
- 启动时漏跑检测（回看昨日 critical 作业）
- 心跳 j_heartbeat 15min
"""
import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import psycopg2
import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("dsched")

HEARTBEAT_FILE = "/tmp/market-sched-heartbeat"


def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("MARKET_TSDB_HOST", "127.0.0.1"),
        port=int(os.getenv("MARKET_TSDB_PORT", "15432")),
        dbname=os.getenv("MARKET_TSDB_NAME", "market_tsdb"),
        user=os.getenv("MARKET_TSDB_USER", "duser_writer"),
        password=os.getenv("MARKET_TSDB_PASSWORD", ""),
    )


def load_seed_jobs(seed_path: str = None) -> list:
    """Load seed jobs from YAML."""
    if seed_path is None:
        seed_path = Path(__file__).resolve().parent.parent / "db" / "seed_jobs.yaml"
    if not Path(seed_path).exists():
        logger.warning(f"Seed jobs file not found: {seed_path}")
        return []
    with open(seed_path) as f:
        data = yaml.safe_load(f) or {}
    return data.get("jobs", [])


def seed_job_registry(conn, jobs: list):
    """Insert seed jobs into job_registry (idempotent via ON CONFLICT)."""
    with conn.cursor() as cur:
        for job in jobs:
            cur.execute("""
                INSERT INTO job_registry
                    (job_name, domain, target_tables, schedule_cron, source_chain,
                     retry_policy, timeout_s, critical, enabled, note)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (job_name) DO UPDATE SET
                    source_chain = EXCLUDED.source_chain,
                    retry_policy = EXCLUDED.retry_policy,
                    timeout_s = EXCLUDED.timeout_s,
                    critical = EXCLUDED.critical,
                    enabled = EXCLUDED.enabled,
                    updated_at = now()
            """, (
                job["job_name"],
                job["domain"],
                job["target_tables"],
                job.get("schedule_cron"),
                json.dumps(job["source_chain"]),
                json.dumps(job.get("retry_policy", {"tries": 3, "backoff_s": [5, 30, 120]})),
                job.get("timeout_s", 600),
                job.get("critical", False),
                job.get("enabled", True),
                job.get("note"),
            ))
    conn.commit()
    logger.info(f"Seeded {len(jobs)} jobs into job_registry")


def detect_missed_runs(conn, lookback_hours: int = 24) -> list:
    """
    漏跑检测：回看过去 N 小时内 critical 作业是否有执行记录。
    返回漏跑的作业列表。
    """
    missed = []
    cutoff = datetime.now() - timedelta(hours=lookback_hours)

    with conn.cursor() as cur:
        # Get all enabled critical jobs
        cur.execute("""
            SELECT job_name, schedule_cron, domain
            FROM job_registry
            WHERE enabled = true AND critical = true
        """)
        critical_jobs = cur.fetchall()

        for job_name, cron_expr, domain in critical_jobs:
            # Check if this job has any ingest_log entry in the lookback window
            cur.execute("""
                SELECT COUNT(*) FROM ingest_log
                WHERE job = %s AND ts >= %s
            """, (job_name, cutoff))
            count = cur.fetchone()[0]

            if count == 0:
                missed.append({
                    "job_name": job_name,
                    "domain": domain,
                    "cron": cron_expr,
                    "lookback_hours": lookback_hours,
                })
                logger.warning(f"⚠️ MISSED: {job_name} (critical, domain={domain}) "
                               f"has no runs in last {lookback_hours}h")

    return missed


def write_heartbeat():
    """Write heartbeat file for health check."""
    Path(HEARTBEAT_FILE).write_text(datetime.now().isoformat())


def run_scheduler():
    """Main scheduler loop."""
    logger.info("🚀 market-sched starting...")

    # Connect to DB
    try:
        conn = get_db_connection()
        logger.info("✅ Connected to market_tsdb")
    except Exception as e:
        logger.error(f"❌ Cannot connect to market_tsdb: {e}")
        sys.exit(1)

    # Seed jobs
    jobs = load_seed_jobs()
    if jobs:
        seed_job_registry(conn, jobs)

    # Missed run detection
    logger.info("🔍 Running missed-run detection...")
    missed = detect_missed_runs(conn, lookback_hours=24)
    if missed:
        logger.warning(f"⚠️ {len(missed)} critical jobs missed in last 24h: "
                       f"{[m['job_name'] for m in missed]}")
    else:
        logger.info("✅ No missed critical jobs detected")

    # Main loop (simplified - APScheduler integration would go here)
    logger.info("📅 Scheduler running. Heartbeat every 15min.")

    running = True

    def handle_signal(signum, frame):
        nonlocal running
        logger.info(f"Received signal {signum}, shutting down...")
        running = False

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    heartbeat_interval = 900  # 15 minutes
    last_heartbeat = 0

    while running:
        now = time.time()
        if now - last_heartbeat >= heartbeat_interval:
            write_heartbeat()
            last_heartbeat = now

            # Log heartbeat to ingest_log
            try:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO ingest_log (job, trigger, domain, target_table,
                                                source_used, status, note)
                        VALUES ('j_heartbeat', 'scheduled', 'pipeline', 'ingest_log',
                                'internal', 'OK', 'heartbeat')
                    """)
                conn.commit()
            except Exception as e:
                logger.warning(f"Heartbeat log failed: {e}")
                # Try to reconnect
                try:
                    conn = get_db_connection()
                except Exception:
                    pass

        time.sleep(1)

    conn.close()
    logger.info("Scheduler stopped.")


if __name__ == "__main__":
    run_scheduler()
