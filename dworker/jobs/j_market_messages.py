"""
j_market_messages - 市场消息采集
- j_market_messages_hot: 核心热点（*/15 9-15 交易日）
- j_market_messages_other: 动态分类（*/8 全天）

移植自 Java MarketTrendsCrawler
"""
import json
import logging
import time
from datetime import datetime
from pathlib import Path

import requests
import yaml

from dworker.core.calendar_gate import check_trade_gate

logger = logging.getLogger(__name__)
SECRETS_PATH = Path(__file__).resolve().parent.parent.parent / "configs" / "secrets.yaml"


def load_secrets():
    with open(SECRETS_PATH) as f:
        return yaml.safe_load(f) or {}


def fetch_hot_messages() -> list:
    """获取核心热点消息（东财/同花顺）"""
    secrets = load_secrets()
    longhu = secrets.get("longhu", {})
    hosts = longhu.get("hosts", {})
    host_url = hosts.get("apparticle", "https://apparticle.longhuvip.com/w1/api/index.php")

    # 东财热点
    try:
        resp = requests.get(f"{host_url}?a=EastmoneyHotMessage", timeout=30)
        data = resp.json()
        return data.get("list", [])
    except Exception as e:
        logger.warning(f"Failed to fetch hot messages: {e}")
        return []


def fetch_category_messages(category_id: str) -> list:
    """获取动态分类消息"""
    secrets = load_secrets()
    longhu = secrets.get("longhu", {})
    hosts = longhu.get("hosts", {})
    host_url = hosts.get("apparticle", "https://apparticle.longhuvip.com/w1/api/index.php")

    try:
        resp = requests.get(f"{host_url}?a=DynamicCategoryMessage&category_id={category_id}", timeout=30)
        data = resp.json()
        return data.get("list", [])
    except Exception as e:
        logger.warning(f"Failed to fetch category {category_id}: {e}")
        return []


def run(job_ctx, deg_chain, source_chain, conn, ingest_logger, raw_archiver, trigger="scheduled"):
    """Execute j_market_messages."""
    t0 = time.time()
    today = datetime.now().strftime("%Y-%m-%d")
    job_name = job_ctx.get("job_name", "j_market_messages") if job_ctx else "j_market_messages"

    # 日历门禁（仅 hot 需要）
    if "hot" in job_name:
        gate = check_trade_gate(conn, market="SSE", check_date=today)
        if not gate["allowed"]:
            note = f"SKIP: {gate['reason']}"
            return {"success": True, "source_used": "none", "rows_in": 0, "rows_written": 0, "rows_quarantined": 0, "note": note}

        # 交易时段检查
        now = datetime.now()
        t = now.hour * 100 + now.minute
        if not (915 <= t <= 1131 or 1300 <= t <= 1501):
            return {"success": True, "source_used": "none", "rows_in": 0, "rows_written": 0, "rows_quarantined": 0, "note": "SKIP: outside trading hours"}

    logger.info(f"[{job_name}] Fetching market messages")

    # Fetch messages
    if "hot" in job_name:
        messages = fetch_hot_messages()
    else:
        # Get active category configs
        with conn.cursor() as cur:
            cur.execute("SELECT id, content FROM dynamic_category_config WHERE status = 1")
            configs = cur.fetchall()
        messages = []
        for cat_id, _ in configs:
            messages.extend(fetch_category_messages(cat_id))

    # Write to market_messages
    written = 0
    for msg in messages:
        try:
            msg_id = str(msg.get("id", ""))
            msg_time = msg.get("time") or msg.get("created_at")
            if not msg_time:
                continue
            ts = f"{today}T{msg_time}+08:00" if "T" not in str(msg_time) else str(msg_time)

            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO market_messages (msg_ts, msg_id, channel, title, content, strength, url, source, ingest_ts)
                    VALUES (%s, %s, 'lovetrade', %s, %s, %s, %s, 'longhu', now())
                    ON CONFLICT (msg_ts, msg_id) DO UPDATE SET
                        title=EXCLUDED.title, content=EXCLUDED.content, source=EXCLUDED.source
                """, (ts, msg_id, msg.get("title", ""), msg.get("content", ""),
                      msg.get("score"), msg.get("url")))
            conn.commit()
            written += 1
        except Exception as e:
            logger.warning(f"Failed to write message: {e}")
            conn.rollback()

    elapsed = time.time() - t0
    note = f"messages written={written} elapsed={elapsed:.1f}s"
    logger.info(f"[{job_name}] {note}")

    return {
        "success": True,
        "source_used": "longhu",
        "rows_in": len(messages),
        "rows_written": written,
        "rows_quarantined": 0,
        "note": note,
    }
