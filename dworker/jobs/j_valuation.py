"""估值。腾讯个股报价的市盈率、市净率、市值，时间戳必须等于目标交易日。"""
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
            ingest_logger.log_run("j_valuation", "auxiliary", "valuation_daily", "none", "SKIP", note=note, trigger=trigger)
        except Exception:
            pass
        return {"success": True, "already_logged": True, "source_used": "none",
                "rows_in": 0, "rows_written": 0, "rows_quarantined": 0, "note": note}

    with conn.cursor() as cur:
        cur.execute("""
            SELECT code FROM instrument_master
            WHERE length(code) = 6 AND code ~ '^[036]'
        """)
        codes = [_prefix(r[0]) for r in cur.fetchall()]
    rows = _quotes(codes, trade_date)
    if not rows:
        return {"success": False, "source_used": "tencent", "rows_in": 0,
                "rows_written": 0, "rows_quarantined": 0,
                "note": f"MISS: no valuation quotes dated {trade_date}"}
    try:
        raw_archiver.archive("D9", "j_valuation", "tencent", rows[:20])
    except Exception as e:
        logger.warning(f"[j_valuation] archive {e}")
    n = _write(conn, rows)
    return {"success": n > 0, "source_used": "tencent",
            "rows_in": len(rows), "rows_written": n, "rows_quarantined": 0,
            "note": f"date={trade_date} symbols={len(codes)} written={n} pe_field=39 pb_field=46 mv_yi"}


def _quotes(codes: list, trade_date: str) -> list:
    ymd = trade_date.replace("-", "")
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com/"})
    rows = []
    for i in range(0, len(codes), 60):
        try:
            resp = session.get("https://qt.gtimg.cn/q=" + ",".join(codes[i:i + 60]), timeout=20)
            text = resp.content.decode("gbk", errors="replace")
        except Exception as e:
            logger.warning(f"[j_valuation] batch {i}: {e}")
            continue
        for line in text.split(";"):
            if "=" not in line:
                continue
            key, val = line.split("=", 1)
            parts = val.strip().strip('"').split("~")
            if len(parts) < 47 or not parts[30].startswith(ymd):
                continue
            rows.append({
                "date": trade_date,
                "code": key.strip().replace("v_", ""),
                "pe_ttm": _num(parts[39]),
                "pb": _num(parts[46]),
                "circ_mv": None if _num(parts[44]) is None else _num(parts[44]) * 1e8,
                "total_mv": None if _num(parts[45]) is None else _num(parts[45]) * 1e8,
            })
    return rows


def _write(conn, rows: list) -> int:
    n = 0
    with conn.cursor() as cur:
        for r in rows:
            cur.execute("""
                INSERT INTO valuation_daily (date, code, pe_ttm, pb, total_mv, circ_mv, source)
                VALUES (%s,%s,%s,%s,%s,%s,'tencent')
                ON CONFLICT (date, code) DO UPDATE SET
                    pe_ttm=EXCLUDED.pe_ttm, pb=EXCLUDED.pb, total_mv=EXCLUDED.total_mv,
                    circ_mv=EXCLUDED.circ_mv, ingest_ts=now()
            """, (r["date"], r["code"], r["pe_ttm"], r["pb"], r["total_mv"], r["circ_mv"]))
            n += 1
    conn.commit()
    return n


def _prefix(code: str) -> str:
    if code.startswith("6"):
        return "sh" + code
    return "sz" + code


def _num(v):
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    if n != n or n < 0:
        return None
    return n
