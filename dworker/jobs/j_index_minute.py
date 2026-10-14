"""六大指数 1 分钟线。腾讯 ifzq 提供 OHLC 和成交量，分钟成交额另取。

成交额先读新浪分钟 K，东财分时作备源。两边的额都是元，和已入库的东财额一致。
成交量继续以腾讯为准，因为分钟量加总能对上日线。东财下午经常直接断开连接，
所以取额要换地址重试；目标日还有空额时，这次任务不算成功。
"""
import json
import logging
import time
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
    missing = _missing_amounts(conn, trade_date)
    return {
        "success": written > 0 and missing == 0,
        "source_used": "tencent+sina",
        "rows_in": len(rows),
        "rows_written": written,
        "rows_quarantined": 0,
        "note": f"date={trade_date} bars={written} amount_rows={amount_n} amount_missing={missing}",
    }


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
    """把分钟成交额写回已有的 index_minute 行。新浪失败再试东财。"""
    total = 0
    for code, _name in INDEX_CODES:
        pairs = _fetch_amounts(code, ndays)
        if not pairs:
            logger.warning(f"[j_index_minute] amount {code}: no rows")
            continue
        total += _write_amounts(conn, pairs)
        time.sleep(0.2)
    return total


def _write_amounts(conn, pairs: list) -> int:
    total = 0
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
    last_error = None
    for attempt, wait in enumerate((0, 1, 3)):
        if wait:
            time.sleep(wait)
        try:
            rows = _fetch_amounts_sina(code, ndays)
            if rows:
                return rows
            last_error = RuntimeError("sina returned no minute amounts")
        except Exception as e:
            last_error = e
            logger.warning(f"[j_index_minute] sina amount {code} try {attempt + 1}: {e}")
    for attempt in range(2):
        if attempt:
            time.sleep(2)
        try:
            rows = _fetch_amounts_eastmoney(code, ndays)
            if rows:
                return rows
        except Exception as e:
            last_error = e
            logger.warning(f"[j_index_minute] eastmoney amount {code} try {attempt + 1}: {e}")
    if last_error:
        logger.warning(f"[j_index_minute] amount {code} gave up: {last_error}")
    return []


def _fetch_amounts_sina(code: str, ndays: int) -> list:
    """新浪分钟 K。day, open, high, low, close, volume, amount。额的单位是元。"""
    datalen = min(1200, max(300, ndays * 260))
    resp = requests.get(
        "https://quotes.sina.cn/cn/api/jsonp.php/var%20_=/CN_MarketDataService.getKLineData",
        params={"symbol": code, "scale": 1, "ma": "no", "datalen": datalen},
        headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn/"},
        timeout=20,
    )
    text = resp.text
    start, end = text.find("(["), text.rfind("])")
    if start < 0 or end < start:
        raise RuntimeError(f"sina minute payload unusable ({resp.status_code})")
    rows = []
    for item in json.loads(text[start + 1:end + 1]):
        stamp = str(item.get("day") or "")
        amount = _num(item.get("amount"))
        if len(stamp) < 16 or amount is None:
            continue
        rows.append((code, stamp[:16] + ":00+08", amount))
    return rows


def _fetch_amounts_eastmoney(code: str, ndays: int) -> list:
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


def _missing_amounts(conn, trade_date: str) -> int:
    codes = tuple(code for code, _name in INDEX_CODES)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*) FROM index_minute
            WHERE freq = '1m' AND amount IS NULL AND volume > 10000
              AND code IN %s
              AND (ts AT TIME ZONE 'Asia/Shanghai')::date = %s
            """,
            (codes, trade_date),
        )
        return cur.fetchone()[0]


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
