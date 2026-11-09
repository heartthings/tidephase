"""
j_radar - 市场雷达采集开盘啦/开盘红大盘直播。

端点 ZhiBoContent / ConceptionPoint。一次返回当天已经发出的直播，不是旧的市场雷达列表。
旧的 HomeDingPan Radar 不再请求。
"""
import json
import logging
import time
from datetime import datetime, timedelta, timezone

from dworker.adapters.longhu import LonghuAdapter
from dworker.core.calendar_gate import check_trade_gate
from dworker.core.degradation import JobContext, SourceError

logger = logging.getLogger(__name__)
TZ = timezone(timedelta(hours=8))
SOURCE = "kaipanla_zhibo"


def run(job_ctx, deg_chain, source_chain, conn, ingest_logger, raw_archiver, trigger="scheduled"):
    """Execute j_radar."""
    t0 = time.time()
    now = datetime.now(TZ)
    today = now.strftime("%Y-%m-%d")

    gate = check_trade_gate(conn, market="SSE", check_date=today)
    if not gate["allowed"]:
        note = f"SKIP: {gate['reason']}"
        logger.info(f"[j_radar] {note}")
        return {"success": True, "source_used": "none", "rows_in": 0, "rows_written": 0, "rows_quarantined": 0, "note": note}

    t = now.hour * 100 + now.minute
    if trigger != "manual" and not (915 <= t <= 1510):
        note = "SKIP: outside trading hours"
        logger.info(f"[j_radar] {note}")
        return {"success": True, "source_used": "none", "rows_in": 0, "rows_written": 0, "rows_quarantined": 0, "note": note}

    logger.info("[j_radar] Fetching kaipanla live broadcast")
    adapter = LonghuAdapter()
    ctx = JobContext("j_radar", "D8", ["radar_event"], {})
    payload = {}
    items = []
    last_error = ""
    for attempt in range(2):
        try:
            result = adapter.fetch(ctx, {"endpoint": "OpeningStockDynamicNews", "extra_params": {}})
        except SourceError as e:
            last_error = str(e)
            time.sleep(3)
            continue
        payload = result.raw_payload or {}
        items = payload.get("List") or []
        if items:
            break
        last_error = "live broadcast empty"
        time.sleep(3)
    if not items:
        return {"success": False, "source_used": SOURCE, "rows_in": 0, "rows_written": 0, "rows_quarantined": 0, "note": f"MISS: {last_error}"}
    day = str(payload.get("date") or today)
    written = 0
    try:
        with conn.cursor() as cur:
            for item in items:
                row = _row(item)
                if row is None:
                    continue
                cur.execute("""
                    INSERT INTO radar_event
                        (ts, event_id, event_type, title, content, related_codes, extra, source, ingest_ts)
                    VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, now())
                    ON CONFLICT (ts, event_id) DO UPDATE SET
                        event_type=EXCLUDED.event_type,
                        title=EXCLUDED.title,
                        content=EXCLUDED.content,
                        related_codes=EXCLUDED.related_codes,
                        extra=EXCLUDED.extra,
                        source=EXCLUDED.source,
                        ingest_ts=now()
                """, (
                    row["ts"], row["event_id"], row["event_type"], row["title"], row["content"],
                    json.dumps(row["related_codes"], ensure_ascii=False),
                    json.dumps(row["extra"], ensure_ascii=False),
                    SOURCE,
                ))
                written += 1
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.warning(f"[j_radar] write failed: {e}")
        return {"success": False, "source_used": SOURCE, "rows_in": len(items), "rows_written": 0, "rows_quarantined": 0, "note": f"EXCEPTION: {e}"}

    elapsed = time.time() - t0
    note = f"zhibo day={day} written={written} elapsed={elapsed:.1f}s"
    logger.info(f"[j_radar] {note}")
    return {
        "success": written > 0,
        "source_used": SOURCE,
        "rows_in": len(items),
        "rows_written": written,
        "rows_quarantined": 0,
        "note": note,
    }


def _row(item: dict) -> dict | None:
    comment = str(item.get("Comment") or "").strip()
    unix = item.get("Time")
    item_id = str(item.get("ID") or "").strip()
    if not comment or unix is None or not item_id:
        return None
    plate = str(item.get("PlateName") or "").strip()
    zdf = str(item.get("PlateZDF") or "").strip()
    stocks = item.get("Stock") if isinstance(item.get("Stock"), list) else []
    codes = []
    names = []
    for stock in stocks:
        if isinstance(stock, list) and stock:
            code = _norm_code(str(stock[0]))
            if code:
                codes.append(code)
            if len(stock) > 1 and stock[1]:
                names.append(str(stock[1]))
    lb = ""
    if zdf:
        lb = zdf if zdf.endswith("%") else f"{zdf}%"
    return {
        "ts": datetime.fromtimestamp(int(unix), TZ),
        "event_id": f"zhibo-{item_id}",
        "event_type": plate or "大盘直播",
        "title": plate or "大盘直播",
        "content": comment,
        "related_codes": codes,
        "extra": {
            "stock_name": plate or "大盘",
            "lb_status": lb,
            "status": "大盘直播",
            "stocks": names[:8],
            "plate_code": str(item.get("PlateCode") or ""),
            "type": str(item.get("Type") or ""),
        },
    }


def _norm_code(raw: str) -> str:
    raw = raw.strip()
    if len(raw) == 6 and raw.isdigit():
        if raw.startswith("6"):
            return f"sh{raw}"
        if raw.startswith(("0", "3")):
            return f"sz{raw}"
        if raw.startswith(("4", "8")):
            return f"bj{raw}"
    return raw
