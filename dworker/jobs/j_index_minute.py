"""六大指数 1 分钟线。腾讯 ifzq mkline，只落目标交易日的 bar。"""
import logging
from datetime import datetime, timedelta, timezone

import requests

from dworker.core.calendar_gate import check_trade_gate
from dworker.jobs.j_index_daily import INDEX_CODES

logger = logging.getLogger(__name__)
TZ = timezone(timedelta(hours=8))


def run(job_ctx, deg_chain, source_chain, conn, ingest_logger, raw_archiver, trigger="scheduled"):
    trade_date = (job_ctx.params or {}).get("date") or datetime.now(TZ).strftime("%Y-%m-%d")
    gate = check_trade_gate(conn, market="SSE", check_date=trade_date)
    if not gate["allowed"]:
        note = f"SKIP: {gate['reason']}"
        try:
            ingest_logger.log_run("j_index_minute", "D1", "index_minute", "none", "SKIP", note=note, trigger=trigger)
        except Exception:
            pass
        return {"success": True, "already_logged": True, "source_used": "none",
                "rows_in": 0, "rows_written": 0, "rows_quarantined": 0, "note": note}

    rows = []
    for code, _name in INDEX_CODES:
        rows.extend(_fetch(code, trade_date))
    if not rows:
        return {"success": False, "source_used": "tencent", "rows_in": 0,
                "rows_written": 0, "rows_quarantined": 0,
                "note": f"MISS: no 1m bars for {trade_date}"}
    try:
        raw_archiver.archive("D1", "j_index_minute", "tencent", rows[:30])
    except Exception as e:
        logger.warning(f"[j_index_minute] archive {e}")
    written = _write(conn, rows)
    return {"success": written > 0, "source_used": "tencent",
            "rows_in": len(rows), "rows_written": written, "rows_quarantined": 0,
            "note": f"date={trade_date} bars={written}"}


def _fetch(code: str, trade_date: str) -> list:
    ymd = trade_date.replace("-", "")
    url = f"https://ifzq.gtimg.cn/appstock/app/kline/mkline?param={code},m1,,400"
    try:
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com/"}, timeout=20)
        bars = ((resp.json().get("data") or {}).get(code) or {}).get("m1") or []
    except Exception as e:
        logger.warning(f"[j_index_minute] {code}: {e}")
        return []
    rows = []
    for bar in bars:
        if not isinstance(bar, list) or len(bar) < 6 or not str(bar[0]).startswith(ymd):
            continue
        stamp = str(bar[0])
        ts = f"{stamp[0:4]}-{stamp[4:6]}-{stamp[6:8]} {stamp[8:10]}:{stamp[10:12]}:00+08"
        rows.append({
            "ts": ts, "code": code,
            "open": _num(bar[1]), "close": _num(bar[2]),
            "high": _num(bar[3]), "low": _num(bar[4]), "volume": _num(bar[5]),
        })
    return rows


def _write(conn, rows: list) -> int:
    n = 0
    with conn.cursor() as cur:
        for r in rows:
            cur.execute("""
                INSERT INTO index_minute (ts, code, freq, open, high, low, close, volume, source)
                VALUES (%s,%s,'1m',%s,%s,%s,%s,%s,'tencent')
                ON CONFLICT (ts, code, freq) DO UPDATE SET
                    open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low,
                    close=EXCLUDED.close, volume=EXCLUDED.volume, ingest_ts=now()
            """, (r["ts"], r["code"], r["open"], r["high"], r["low"], r["close"], r["volume"]))
            n += 1
    conn.commit()
    return n


def _num(v):
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return None if n != n else n
