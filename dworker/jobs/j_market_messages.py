"""
j_market_messages - 市场消息采集（不经过 lovetrade-service）

- j_market_messages_hot: 交易时段快讯（*/15 9-15 交易日）
- j_market_messages_other: 7x24 快讯（*/8 全天）

主源东财 7x24 快讯，备源新浪财经滚动。两源都空则写 MISS，不编数。
"""
import json
import logging
import time
from datetime import datetime

import requests

from dworker.core.calendar_gate import check_trade_gate

logger = logging.getLogger(__name__)

EASTMONEY_URL = "https://newsapi.eastmoney.com/kuaixun/v1/getlist_102_ajaxResult_50_1_.html"
SINA_URL = "https://feed.mix.sina.com.cn/api/roll/get"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://kuaixun.eastmoney.com/",
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


def _fetch_eastmoney():
    resp = requests.get(EASTMONEY_URL, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    text = resp.text
    start = text.find("{")
    payload = json.loads(text[start:])
    rows = []
    for item in payload.get("LivesList") or []:
        news_id = str(item.get("newsid") or item.get("id") or "")
        showtime = item.get("showtime")
        title = item.get("title") or item.get("simtitle") or ""
        if not news_id or not showtime or not title:
            continue
        rows.append({
            "msg_id": news_id,
            "msg_ts": f"{showtime}+08:00",
            "title": title,
            "content": item.get("digest") or item.get("simdigest") or title,
            "url": item.get("url_w") or item.get("url_unique"),
        })
    return rows, payload


def _fetch_sina():
    resp = requests.get(
        SINA_URL,
        params={"pageid": 153, "lid": 2509, "num": 20, "page": 1},
        headers=HEADERS,
        timeout=20,
    )
    resp.raise_for_status()
    payload = resp.json()
    items = (((payload or {}).get("result") or {}).get("data") or [])
    rows = []
    for item in items:
        news_id = str(item.get("docid") or item.get("oid") or "")
        title = item.get("title") or ""
        ctime = item.get("ctime") or item.get("intime")
        if not news_id or not title or not ctime:
            continue
        try:
            ts = datetime.fromtimestamp(int(ctime)).strftime("%Y-%m-%d %H:%M:%S+08:00")
        except (TypeError, ValueError):
            continue
        rows.append({
            "msg_id": news_id,
            "msg_ts": ts,
            "title": title,
            "content": item.get("intro") or item.get("summary") or title,
            "url": item.get("url"),
        })
    return rows, payload


def _fetch():
    errors = []
    for source, fn in (("eastmoney", _fetch_eastmoney), ("sina", _fetch_sina)):
        try:
            rows, raw = fn()
            if rows:
                return source, rows, raw
            errors.append(f"{source}: empty")
        except Exception as e:
            errors.append(f"{source}: {e}")
            logger.warning(f"market messages {source} failed: {e}")
    return None, [], {"errors": errors}


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
        note = "MISS: eastmoney and sina returned no rows"
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
