"""
j_market_messages - 市场消息采集（不经过 lovetrade-service）

- j_market_messages_hot: 交易时段快讯（*/15 9-15 交易日）
- j_market_messages_other: 7x24 快讯（*/8 全天）

消息入口只有财联社电报。东财、新浪不再作为快讯源。财联社空或失败则写 MISS，不编数。
"""
import hashlib
import json
import logging
import time
from datetime import datetime

import requests

from dworker.core.calendar_gate import check_trade_gate

logger = logging.getLogger(__name__)

CLS_URL = "https://www.cls.cn/v1/roll/get_roll_list"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.cls.cn/",
    "Accept": "application/json,text/plain,*/*",
}


def _job_name(job_ctx) -> str:
    name = getattr(job_ctx, "job_name", None)
    if name:
        return name
    if isinstance(job_ctx, dict):
        return job_ctx.get("job_name") or "j_market_messages_other"
    return "j_market_messages_other"


def _skip(ingest_logger, job_name, trigger, note):
    ingest_logger.log_run(
        job_name=job_name, domain="D10", target_table="market_messages",
        source_used="none", status="SKIP", rows_in=0, rows_written=0,
        note=note, trigger=trigger,
    )
    return {
        "success": True, "already_logged": True, "source_used": "none",
        "rows_in": 0, "rows_written": 0, "rows_quarantined": 0, "note": note,
    }


def _cls_sign(params: dict) -> str:
    qs = "&".join(f"{k}={params[k]}" for k in sorted(params))
    return hashlib.md5(hashlib.sha1(qs.encode()).hexdigest().encode()).hexdigest()


def _fetch_cls():
    """财联社电报最新一页。8 分钟一轮取 50 条，忙时一页盖得住。"""
    params = {
        "appName": "CailianpressWeb",
        "os": "web",
        "sv": "7.7.5",
        "last_time": "",
        "refresh_type": "1",
        "rn": "50",
    }
    qs = "&".join(f"{k}={params[k]}" for k in sorted(params))
    url = f"{CLS_URL}?{qs}&sign={_cls_sign(params)}"
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("errno") not in (0, None):
        raise RuntimeError(f"cls errno={payload.get('errno')}")
    rows = []
    for item in (payload.get("data") or {}).get("roll_data") or []:
        news_id = str(item.get("id") or "")
        ctime = item.get("ctime")
        title = (item.get("title") or "").strip()
        content = (item.get("brief") or item.get("content") or "").strip()
        if not news_id or not ctime or not (title or content):
            continue
        rows.append({
            "msg_id": news_id,
            "msg_ts": datetime.fromtimestamp(int(ctime)).strftime("%Y-%m-%d %H:%M:%S+08:00"),
            "title": title or content[:80],
            "content": content or title,
            "url": item.get("shareurl") or item.get("assocArticleUrl"),
        })
    return rows, payload


def _fetch():
    try:
        rows, raw = _fetch_cls()
        if rows:
            return "cls", rows, raw
        return None, [], {"errors": ["cls: empty"]}
    except Exception as e:
        logger.warning(f"market messages cls failed: {e}")
        return None, [], {"errors": [f"cls: {e}"]}


def run(job_ctx, deg_chain, source_chain, conn, ingest_logger, raw_archiver, trigger="scheduled"):
    """Execute j_market_messages_hot / j_market_messages_other."""
    t0 = time.time()
    today = datetime.now().strftime("%Y-%m-%d")
    job_name = _job_name(job_ctx)

    if "hot" in job_name:
        gate = check_trade_gate(conn, market="SSE", check_date=today)
        if not gate["allowed"]:
            return _skip(ingest_logger, job_name, trigger, f"SKIP: {gate['reason']}")
        now = datetime.now()
        t = now.hour * 100 + now.minute
        if not (915 <= t <= 1131 or 1300 <= t <= 1501):
            return _skip(ingest_logger, job_name, trigger, "SKIP: outside trading hours")

    source, messages, raw = _fetch()
    if raw_archiver is not None:
        raw_archiver.archive("D10", job_name, source or "none", raw)

    if not messages:
        note = "MISS: cls returned no rows"
        ingest_logger.log_run(
            job_name=job_name, domain="D10", target_table="market_messages",
            source_used="none", status="MISS", rows_in=0, rows_written=0,
            duration_ms=int((time.time() - t0) * 1000), note=note, trigger=trigger,
        )
        return {
            "success": True, "already_logged": True, "source_used": "none",
            "rows_in": 0, "rows_written": 0, "rows_quarantined": 0, "note": note,
        }

    written = 0
    for msg in messages:
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO market_messages
                        (msg_ts, msg_id, channel, title, content, url, source, ingest_ts)
                    VALUES (%s, %s, 'kuaixun', %s, %s, %s, %s, now())
                    ON CONFLICT (msg_ts, msg_id) DO UPDATE SET
                        title = EXCLUDED.title,
                        content = EXCLUDED.content,
                        url = EXCLUDED.url,
                        source = EXCLUDED.source
                """, (
                    msg["msg_ts"], msg["msg_id"], msg["title"], msg["content"],
                    msg["url"], source,
                ))
            conn.commit()
            written += 1
        except Exception as e:
            logger.warning(f"Failed to write message {msg.get('msg_id')}: {e}")
            conn.rollback()

    elapsed = time.time() - t0
    note = f"source={source} written={written} elapsed={elapsed:.1f}s"
    logger.info(f"[{job_name}] {note}")
    return {
        "success": written > 0,
        "source_used": source,
        "rows_in": len(messages),
        "rows_written": written,
        "rows_quarantined": 0,
        "note": note,
    }
