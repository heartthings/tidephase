"""观察池 1 分钟线。只采 watchlist.active 的代码。池子空则 SKIP，不扫全市场。"""
import logging
from datetime import datetime, timedelta, timezone

import requests

from dworker.core.calendar_gate import check_trade_gate

logger = logging.getLogger(__name__)
TZ = timezone(timedelta(hours=8))


def run(job_ctx, deg_chain, source_chain, conn, ingest_logger, raw_archiver, trigger="scheduled"):
    trade_date = (job_ctx.params or {}).get("date") or datetime.now(TZ).strftime("%Y-%m-%d")
    gate = check_trade_gate(conn, market="SSE", check_date=trade_date)
    if not gate["allowed"]:
        note = f"SKIP: {gate['reason']}"
        try:
            ingest_logger.log_run("j_stock_minute", "D2", "stock_minute", "none", "SKIP", note=note, trigger=trigger)
        except Exception:
            pass
        return {"success": True, "already_logged": True, "source_used": "none",
                "rows_in": 0, "rows_written": 0, "rows_quarantined": 0, "note": note}

    with conn.cursor() as cur:
        cur.execute("SELECT code FROM watchlist WHERE active = true")
        codes = [r[0] for r in cur.fetchall()]
    if not codes:
        note = "SKIP: watchlist empty"
        try:
            ingest_logger.log_run("j_stock_minute", "D2", "stock_minute", "none", "SKIP", note=note, trigger=trigger)
        except Exception:
            pass
        return {"success": True, "already_logged": True, "source_used": "none",
                "rows_in": 0, "rows_written": 0, "rows_quarantined": 0, "note": note}

    rows = []
    for code in codes:
        rows.extend(_fetch(code, trade_date))
    if not rows:
        return {"success": False, "source_used": "tencent", "rows_in": 0,
                "rows_written": 0, "rows_quarantined": 0,
                "note": f"MISS: no 1m bars for {trade_date} codes={codes}"}
    try:
        raw_archiver.archive("D2", "j_stock_minute", "tencent", rows[:20])
    except Exception as e:
        logger.warning(f"[j_stock_minute] archive {e}")
    n = _write(conn, rows)
    return {"success": n > 0, "source_used": "tencent",
            "rows_in": len(rows), "rows_written": n, "rows_quarantined": 0,
            "note": f"date={trade_date} codes={len(codes)} bars={n}"}


def _fetch(code: str, trade_date: str) -> list:
    ymd = trade_date.replace("-", "")
    url = f"https://ifzq.gtimg.cn/appstock/app/kline/mkline?param={code},m1,,400"
    try:
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        bars = ((resp.json().get("data") or {}).get(code) or {}).get("m1") or []
    except Exception as e:
        logger.warning(f"[j_stock_minute] {code}: {e}")
        return []
    rows = []
    for bar in bars:
        if not isinstance(bar, list) or len(bar) < 6 or not str(bar[0]).startswith(ymd):
            continue
        stamp = str(bar[0])
        ts = f"{stamp[0:4]}-{stamp[4:6]}-{stamp[6:8]} {stamp[8:10]}:{stamp[10:12]}:00+08"
        close = _num(bar[2])
        rows.append({
            "ts": ts, "code": code, "price": close,
            "open": _num(bar[1]), "high": _num(bar[3]), "low": _num(bar[4]),
            "vol": _num(bar[5]),
        })
    return rows


def _write(conn, rows: list) -> int:
    n = 0
    with conn.cursor() as cur:
        for r in rows:
            cur.execute("""
                INSERT INTO stock_minute (ts, code, freq, price, open, high, low, vol, source)
                VALUES (%s,%s,'1m',%s,%s,%s,%s,%s,'tencent')
                ON CONFLICT (ts, code, freq) DO UPDATE SET
                    price=EXCLUDED.price, open=EXCLUDED.open, high=EXCLUDED.high,
                    low=EXCLUDED.low, vol=EXCLUDED.vol, ingest_ts=now()
            """, (r["ts"], r["code"], r["price"], r["open"], r["high"], r["low"], r["vol"]))
            n += 1
    conn.commit()
    return n


def _num(v):
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return None if n != n else n
