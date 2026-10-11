"""ETF 日K。新浪拿代码，腾讯报价带交易日时间戳，只写时间戳当天。"""
import logging
import time
from datetime import datetime, timedelta, timezone

import requests

from dworker.core.calendar_gate import check_trade_gate

logger = logging.getLogger(__name__)
TZ = timezone(timedelta(hours=8))


def run(job_ctx, deg_chain, source_chain, conn, ingest_logger, raw_archiver, trigger="scheduled"):
    trade_date = (job_ctx.params or {}).get("date") or datetime.now(TZ).strftime("%Y-%m-%d")
    gate = check_trade_gate(conn, market="SSE", check_date=trade_date)
    if not gate["allowed"]:
        return _skip(ingest_logger, trigger, gate["reason"])

    codes = _sina_etf_codes()
    rows = _tencent_quotes(codes, trade_date)
    if not rows:
        return {"success": False, "source_used": "tencent", "rows_in": 0,
                "rows_written": 0, "rows_quarantined": 0,
                "note": f"MISS: no etf quotes dated {trade_date}"}
    try:
        raw_archiver.archive("D2", "j_etf_daily", "tencent", rows[:20])
    except Exception as e:
        logger.warning(f"[j_etf_daily] archive {e}")
    written = _write(conn, rows)
    return {"success": written > 0, "source_used": "tencent",
            "rows_in": len(rows), "rows_written": written, "rows_quarantined": 0,
            "note": f"date={trade_date} symbols={len(codes)} written={written}"}


def _sina_etf_codes() -> list:
    codes = []
    for page in range(1, 25):
        url = ("https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
               f"Market_Center.getHQNodeData?page={page}&num=100&sort=symbol&asc=1&node=etf_hq_fund")
        try:
            resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0",
                                              "Referer": "https://vip.stock.finance.sina.com.cn/"}, timeout=20)
            batch = resp.json()
        except Exception as e:
            logger.warning(f"[j_etf_daily] sina page {page}: {e}")
            break
        if not isinstance(batch, list) or not batch:
            break
        for item in batch:
            sym = str(item.get("symbol") or "")
            if sym.startswith(("sh", "sz")):
                codes.append(sym)
        if len(batch) < 100:
            break
        time.sleep(0.1)
    return codes


def _tencent_quotes(codes: list, trade_date: str) -> list:
    ymd = trade_date.replace("-", "")
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com/"})
    rows = []
    for i in range(0, len(codes), 60):
        query = ",".join(codes[i:i + 60])
        try:
            resp = session.get(f"https://qt.gtimg.cn/q={query}", timeout=20)
            text = resp.content.decode("gbk", errors="replace")
        except Exception as e:
            logger.warning(f"[j_etf_daily] tencent batch: {e}")
            continue
        for line in text.split(";"):
            if "=" not in line:
                continue
            key, val = line.split("=", 1)
            parts = val.strip().strip('"').split("~")
            if len(parts) < 38 or not parts[30].startswith(ymd):
                continue
            close = _num(parts[3])
            if close is None or close <= 0:
                continue
            code = key.strip().replace("v_", "")
            rows.append({
                "date": trade_date, "code": code, "name": parts[1],
                "open": _num(parts[5]), "high": _num(parts[33]), "low": _num(parts[34]),
                "close": close, "pct": _num(parts[32]),
                "volume": _num(parts[6]),
                "amount": None if _num(parts[37]) is None else _num(parts[37]) * 10000,
            })
    return rows


def _write(conn, rows: list) -> int:
    n = 0
    with conn.cursor() as cur:
        for r in rows:
            cur.execute("""
                INSERT INTO etf_daily (date, code, name, open, high, low, close, pct, volume, amount, source)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'tencent')
                ON CONFLICT (date, code) DO UPDATE SET
                    name=EXCLUDED.name, open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low,
                    close=EXCLUDED.close, pct=EXCLUDED.pct, volume=EXCLUDED.volume,
                    amount=EXCLUDED.amount, source=EXCLUDED.source, ingest_ts=now()
            """, (r["date"], r["code"], r["name"], r["open"], r["high"], r["low"],
                  r["close"], r["pct"], r["volume"], r["amount"]))
            n += 1
    conn.commit()
    return n


def _num(v):
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    if n != n:
        return None
    return n


def _skip(ingest_logger, trigger, reason):
    note = f"SKIP: {reason}"
    try:
        ingest_logger.log_run("j_etf_daily", "D2", "etf_daily", "none", "SKIP", note=note, trigger=trigger)
    except Exception:
        pass
    return {"success": True, "already_logged": True, "source_used": "none",
            "rows_in": 0, "rows_written": 0, "rows_quarantined": 0, "note": note}
