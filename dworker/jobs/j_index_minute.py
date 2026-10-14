"""六大指数 1 分钟线。腾讯 ifzq 提供 OHLC 和成交量，东财分时补成交额。

定时任务只落目标交易日的分钟 bar，同时把东财最近几个交易日的分钟成交额
回写到已经存在的分钟行上。成交量继续以腾讯为准，因为分钟量加总能对上日线。
"""
import logging
from datetime import datetime, timedelta, timezone

import requests
from psycopg2.extras import execute_values

from dworker.core.calendar_gate import check_trade_gate
from dworker.jobs.j_index_daily import INDEX_CODES

logger = logging.getLogger(__name__)
TZ = timezone(timedelta(hours=8))
EASTMONEY_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"}


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
    amount_days = int((job_ctx.params or {}).get("amount_days") or 5)
    amount_n = _sync_amount(conn, amount_days)
    return {"success": written > 0, "source_used": "tencent+eastmoney",
            "rows_in": len(rows), "rows_written": written, "rows_quarantined": 0,
            "note": f"date={trade_date} bars={written} amount_rows={amount_n}"}


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


def _sync_amount(conn, ndays: int) -> int:
    """把东财分时里的分钟成交额写回已有的 index_minute 行。"""
    total = 0
    for code, _name in INDEX_CODES:
        try:
            pairs = _fetch_amounts(code, ndays)
        except Exception as e:
            logger.warning(f"[j_index_minute] amount {code}: {e}")
            continue
        if not pairs:
            continue
        with conn.cursor() as cur:
            for i in range(0, len(pairs), 2000):
                execute_values(
                    cur,
                    """
                    UPDATE index_minute AS m
                    SET amount = v.amount, ingest_ts = now()
                    FROM (VALUES %s) AS v(code, ts, amount)
                    WHERE m.code = v.code AND m.freq = '1m' AND m.ts = v.ts
                    """,
                    pairs[i:i + 2000],
                    template="(%s, %s::timestamptz, %s::float8)",
                    page_size=2000,
                )
                total += max(cur.rowcount, 0)
        conn.commit()
    return total


def _fetch_amounts(code: str, ndays: int) -> list:
    """东财 trends2：time, 占位, close, high, low, volume, amount, avg。"""
    secid = ("1." if code.startswith("sh") else "0.") + code[2:]
    resp = requests.get(
        "https://push2his.eastmoney.com/api/qt/stock/trends2/get",
        params={
            "secid": secid,
            "ndays": str(max(1, ndays)),
            "iscr": "0",
            "fields1": "f1,f2,f3,f4,f5,f6,f7,f8",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
        },
        headers=EASTMONEY_HEADERS,
        timeout=20,
    )
    trends = ((resp.json().get("data") or {}).get("trends")) or []
    rows = []
    for line in trends:
        parts = str(line).split(",")
        if len(parts) < 7 or len(parts[0]) < 16:
            continue
        amount = _num(parts[6])
        if amount is None:
            continue
        rows.append((code, parts[0][:16] + ":00+08", amount))
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
