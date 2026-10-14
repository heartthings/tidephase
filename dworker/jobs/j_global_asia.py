"""港股收盘。腾讯恒生、国企指数。报价里的日期必须等于目标交易日。"""
import logging
from datetime import datetime, timedelta, timezone

import requests

from dworker.core.calendar_gate import check_trade_gate

logger = logging.getLogger(__name__)
TZ = timezone(timedelta(hours=8))
CODES = (("hkHSI", "HSI", "HK", "恒生指数"), ("hkHSCEI", "HSCEI", "HK", "国企指数"))


def run(job_ctx, deg_chain, source_chain, conn, ingest_logger, raw_archiver, trigger="scheduled"):
    trade_date = (job_ctx.params or {}).get("date") or datetime.now(TZ).strftime("%Y-%m-%d")
    gate = check_trade_gate(conn, market="SSE", check_date=trade_date)
    if not gate["allowed"]:
        note = f"SKIP: {gate['reason']}"
        try:
            ingest_logger.log_run("j_global_asia", "D7", "global_daily", "none", "SKIP", note=note, trigger=trigger)
        except Exception:
            pass
        return {"success": True, "already_logged": True, "source_used": "none",
                "rows_in": 0, "rows_written": 0, "rows_quarantined": 0, "note": note}

    now = datetime.now(TZ)
    if trade_date == now.strftime("%Y-%m-%d") and now.hour < 16:
        return {"success": True, "source_used": "none", "rows_in": 0,
                "rows_written": 0, "rows_quarantined": 0,
                "note": f"SKIP: HK cash session not closed yet ({trade_date})"}
    rows = _fetch(trade_date)
    if not rows:
        return {"success": False, "source_used": "tencent", "rows_in": 0,
                "rows_written": 0, "rows_quarantined": 0,
                "note": f"MISS: no HK quotes dated {trade_date}"}
    try:
        raw_archiver.archive("D7", "j_global_asia", "tencent", rows)
    except Exception as e:
        logger.warning(f"[j_global_asia] archive {e}")
    n = _write(conn, rows)
    return {"success": n > 0, "source_used": "tencent",
            "rows_in": len(rows), "rows_written": n, "rows_quarantined": 0,
            "note": f"date={trade_date} hk={n}"}


def _fetch(trade_date: str) -> list:
    query = ",".join(c[0] for c in CODES)
    try:
        resp = requests.get(f"https://qt.gtimg.cn/q={query}",
                            headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        text = resp.content.decode("gbk", errors="replace")
    except Exception as e:
        logger.warning(f"[j_global_asia] {e}")
        return []
    wanted = {c[0]: c for c in CODES}
    rows = []
    for line in text.split(";"):
        if "=" not in line:
            continue
        key, val = line.split("=", 1)
        info = wanted.get(key.strip().replace("v_", ""))
        parts = val.strip().strip('"').split("~")
        if not info or len(parts) < 35:
            continue
        stamp = parts[30].replace("/", "-").split(" ")[0]
        if stamp != trade_date:
            continue
        close = _num(parts[3])
        if close is None or close <= 0:
            continue
        rows.append({
            "date": trade_date, "market": info[2], "code": info[1], "name": info[3],
            "close": close, "pct": _num(parts[32]),
            "open": _num(parts[5]), "high": _num(parts[33]), "low": _num(parts[34]),
            "volume": _num(parts[6]),
        })
    return rows


def _write(conn, rows: list) -> int:
    n = 0
    with conn.cursor() as cur:
        for r in rows:
            cur.execute("""
                INSERT INTO global_daily
                    (date, market, code, name, session, open, high, low, close, pct, volume, source)
                VALUES (%s,%s,%s,%s,'close',%s,%s,%s,%s,%s,%s,'tencent')
                ON CONFLICT (date, code, session) DO UPDATE SET
                    name=EXCLUDED.name, open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low,
                    close=EXCLUDED.close, pct=EXCLUDED.pct, volume=EXCLUDED.volume, ingest_ts=now()
            """, (r["date"], r["market"], r["code"], r["name"], r["open"], r["high"],
                  r["low"], r["close"], r["pct"], r["volume"]))
            n += 1
    conn.commit()
    return n


def _num(v):
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return None if n != n else n
