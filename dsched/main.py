"""
dsched - 真调度服务（Z4c 热修）
APScheduler BlockingScheduler + job_registry 唯一事实源。
功能：
- cron 调度（Asia/Shanghai）
- 按 job_registry.schedule_cron 逐条注册
- 超时强制中断
- 启动时漏跑检测
- 心跳 j_heartbeat 15min
- 每次 run 写 ingest_log 完整字段
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
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

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
        # Try both container path and dev path
        for p in [
            Path(__file__).resolve().parent.parent / "db" / "seed_jobs.yaml",
            Path("/app/db/seed_jobs.yaml"),
        ]:
            if p.exists():
                seed_path = str(p)
                break
    if not seed_path or not Path(seed_path).exists():
        logger.warning(f"Seed jobs file not found")
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
                    schedule_cron = EXCLUDED.schedule_cron,
                    note = EXCLUDED.note,
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
    """漏跑检测：回看过去 N 小时内 critical 作业是否有执行记录。"""
    missed = []
    cutoff = datetime.now() - timedelta(hours=lookback_hours)

    with conn.cursor() as cur:
        cur.execute("""
            SELECT job_name, schedule_cron, domain
            FROM job_registry
            WHERE enabled = true AND critical = true
        """)
        critical_jobs = cur.fetchall()

        for job_name, cron_expr, domain in critical_jobs:
            cur.execute("""
                SELECT COUNT(*) FROM ingest_log
                WHERE job = %s AND ts >= %s AND trigger != 'heartbeat'
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


def write_heartbeat(conn):
    """Write heartbeat file + ingest_log row."""
    Path(HEARTBEAT_FILE).write_text(datetime.now().isoformat())
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


def _cron_dow_to_apscheduler(field: str) -> str:
    """标准 cron 周几（0 或 7=周日，1=周一）转成 APScheduler 的周名。"""
    if not field or field == "*" or any(c.isalpha() for c in field):
        return field
    names = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"]

    def one(token: str) -> str:
        step = ""
        if "/" in token:
            token, step_n = token.split("/", 1)
            step = "/" + step_n
        if "-" in token:
            a, b = token.split("-", 1)
            return f"{names[int(a) % 7]}-{names[int(b) % 7]}{step}"
        return f"{names[int(token) % 7]}{step}"

    return ",".join(one(part) for part in field.split(",") if part)


def parse_cron_expression(cron_expr: str) -> dict:
    """
    Parse cron expression (5-field) into APScheduler CronTrigger kwargs.
    Format: "minute hour day month day_of_week"
    """
    if not cron_expr or cron_expr.strip() == "":
        return None

    parts = cron_expr.strip().split()
    if len(parts) != 5:
        logger.warning(f"Invalid cron expression: {cron_expr}")
        return None

    minute, hour, day, month, day_of_week = parts
    # APScheduler day_of_week 是 0=周一。标准 cron 是 0=周日。
    # 直接把 "1-5" 塞进去会变成周二到周六：周一不开火、周六误开火。
    day_of_week = _cron_dow_to_apscheduler(day_of_week)

    kwargs = {}
    if minute != "*":
        if "/" in minute:
            kwargs["minute"] = f"*/{minute.split('/')[1]}"
        else:
            kwargs["minute"] = minute
    if hour != "*":
        if "/" in hour:
            kwargs["hour"] = f"*/{hour.split('/')[1]}"
        else:
            kwargs["hour"] = hour
    if day != "*":
        kwargs["day"] = day
    if month != "*":
        kwargs["month"] = month
    if day_of_week != "*":
        kwargs["day_of_week"] = day_of_week

    return kwargs


def job_dispatch(job_name: str, conn_str: str = None):
    """
    Dispatch a job by name. Called by APScheduler on cron trigger.
    Imports and calls dworker.core.runner.execute_job.
    """
    logger.info(f"🔔 CRON FIRED: {job_name}")
    try:
        # Re-import to avoid stale state
        from dworker.core.runner import execute_job, get_db_connection
        success, note = execute_job(job_name, trigger="scheduled")
        logger.info(f"✅ {job_name} completed: success={success} note={note}")
    except Exception as e:
        logger.error(f"❌ {job_name} dispatch failed: {e}")
        import traceback
        traceback.print_exc()


def run_scheduler():
    """Main scheduler with APScheduler."""
    logger.info("🚀 market-sched starting (APScheduler BlockingScheduler)...")

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

    # Initialize APScheduler
    scheduler = BlockingScheduler(timezone="Asia/Shanghai")

    # Load all enabled jobs from job_registry and register with APScheduler
    with conn.cursor() as cur:
        cur.execute("""
            SELECT job_name, schedule_cron, enabled
            FROM job_registry
            WHERE enabled = true AND schedule_cron IS NOT NULL
        """)
        db_jobs = cur.fetchall()

    registered = 0
    for job_name, cron_expr, enabled in db_jobs:
        if job_name == "j_heartbeat":
            # Heartbeat handled separately
            continue

        cron_kwargs = parse_cron_expression(cron_expr)
        if cron_kwargs is None:
            logger.warning(f"⚠️ Cannot parse cron for {job_name}: {cron_expr}")
            continue

        try:
            trigger = CronTrigger(**cron_kwargs, timezone="Asia/Shanghai")
            scheduler.add_job(
                job_dispatch,
                trigger=trigger,
                args=[job_name],
                id=job_name,
                name=job_name,
                misfire_grace_time=3600,  # 1 hour grace period
                coalesce=True,  # Merge missed runs into one
            )
            registered += 1
            logger.info(f"📅 Registered: {job_name} cron={cron_expr}")
        except Exception as e:
            logger.error(f"❌ Failed to register {job_name}: {e}")

    # Heartbeat job (every 15 min)
    scheduler.add_job(
        write_heartbeat,
        trigger=CronTrigger(minute="*/15", timezone="Asia/Shanghai"),
        args=[conn],
        id="j_heartbeat_internal",
        name="heartbeat",
        misfire_grace_time=60,
    )

    logger.info(f"✅ Registered {registered} jobs + heartbeat")
    logger.info(f"📋 Scheduled jobs: {[j.id for j in scheduler.get_jobs()]}")

    # Write initial heartbeat
    write_heartbeat(conn)

    # Signal handlers
    def handle_signal(signum, frame):
        logger.info(f"Received signal {signum}, shutting down scheduler...")
        scheduler.shutdown(wait=False)

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    # Start scheduler (blocking)
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    run_scheduler()
