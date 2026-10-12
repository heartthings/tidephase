"""全市场个股 1 分钟线。

沪深：腾讯 mkline，最近 400 根（约一个半交易日）。
北交所：mkline 没有分钟 K，用分时（只有现价和成交量，当天）。
定时任务只落目标交易日。手工触发不带 date 时，把这次返回里的交易日都落上。
"""
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import requests
from psycopg2.extras import execute_values

from dworker.core.calendar_gate import check_trade_gate

logger = logging.getLogger(__name__)
TZ = timezone(timedelta(hours=8))
WORKERS = 8
BARS = 400
BATCH = 80


def run(job_ctx, deg_chain, source_chain, conn, ingest_logger, raw_archiver, trigger="scheduled"):
    only_date = (job_ctx.params or {}).get("date")
    trade_date = only_date or datetime.now(TZ).strftime("%Y-%m-%d")
    # 定时任务只写当天。手工触发不指定日期时，保留接口窗口里的全部交易日。
    keep_date = trade_date if (trigger == "scheduled" or only_date) else None
    gate = check_trade_gate(conn, market="SSE", check_date=trade_date)
    if not gate["allowed"]:
        note = f"SKIP: {gate['reason']}"
        try:
            ingest_logger.log_run("j_stock_minute", "D2", "stock_minute", "none", "SKIP", note=note, trigger=trigger)
        except Exception:
            pass
        return {"success": True, "already_logged": True, "source_used": "none",
                "rows_in": 0, "rows_written": 0, "rows_quarantined": 0, "note": note}

    codes = _load_codes(conn)
    if not codes:
        return {"success": False, "source_used": "tencent", "rows_in": 0,
                "rows_written": 0, "rows_quarantined": 0, "note": "MISS: no active stocks"}

    written = 0
    empty = 0
    errors = 0
    dates = set()
    sample = []
    for i in range(0, len(codes), BATCH):
        batch = codes[i:i + BATCH]
        rows, batch_empty, batch_errors, batch_dates = _fetch_batch(batch, keep_date)
        empty += batch_empty
        errors += batch_errors
        dates |= batch_dates
        if rows and not sample:
            sample = rows[:20]
        written += _write(conn, rows)
        logger.info(
            f"[j_stock_minute] {min(i + BATCH, len(codes))}/{len(codes)} "
            f"written={written} empty={empty} errors={errors}"
        )

    if sample:
        try:
            raw_archiver.archive("D2", "j_stock_minute", "tencent", sample)
        except Exception as e:
            logger.warning(f"[j_stock_minute] archive {e}")

    note = (
        f"date={keep_date or 'window'} codes={len(codes)} bars={written} "
        f"empty={empty} errors={errors} days={','.join(sorted(dates)) or '-'}"
    )
    covered = len(codes) - errors
    return {"success": written > 0 and errors < covered, "source_used": "tencent",
            "rows_in": written, "rows_written": written, "rows_quarantined": 0, "note": note}


def _load_codes(conn) -> list:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT code FROM instrument_master
            WHERE inst_type = 'stock' AND status = 'active'
            ORDER BY code
        """)
        return [_prefix(r[0]) for r in cur.fetchall()]


def _prefix(code: str) -> str:
    if code.startswith(("60", "68")):
        return "sh" + code
    if code.startswith(("43", "83", "87", "92")):
        return "bj" + code
    return "sz" + code


def _fetch_batch(codes: list, keep_date):
    rows = []
    empty = 0
    errors = 0
    dates = set()
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for got, ok, dayset in pool.map(lambda c: _fetch(c, keep_date), codes):
            if not ok:
                errors += 1
                continue
            if not got:
                empty += 1
                continue
            rows.extend(got)
            dates |= dayset
    return rows, empty, errors, dates


def _fetch(code: str, keep_date):
    last = None
    for attempt in range(2):
        try:
            if code.startswith("bj"):
                rows = _fetch_trend(code, keep_date)
            else:
                rows = _fetch_mkline(code, keep_date)
            return rows, True, {r[0][0:10] for r in rows}
        except Exception as e:
            last = e
            time.sleep(1.5)
    logger.warning(f"[j_stock_minute] {code}: {last}")
    return [], False, set()


def _fetch_mkline(code: str, keep_date) -> list:
    url = f"https://ifzq.gtimg.cn/appstock/app/kline/mkline?param={code},m1,,{BARS}"
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
    bars = ((resp.json().get("data") or {}).get(code) or {}).get("m1") or []
    rows = []
    for bar in bars:
        if not isinstance(bar, list) or len(bar) < 6:
            continue
        stamp = str(bar[0])
        if len(stamp) < 12:
            continue
        day = f"{stamp[0:4]}-{stamp[4:6]}-{stamp[6:8]}"
        if keep_date and day != keep_date:
            continue
        ts = f"{day} {stamp[8:10]}:{stamp[10:12]}:00+08"
        rows.append((
            ts, code, _num(bar[2]), _num(bar[1]), _num(bar[3]), _num(bar[4]), _num(bar[5]),
        ))
    return rows


def _fetch_trend(code: str, keep_date) -> list:
    """北交所分时。每根只有现价和累计成交量，开高低用现价。"""
    url = f"https://web.ifzq.gtimg.cn/appstock/app/minute/query?code={code}"
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com/"}, timeout=20)
    node = ((resp.json().get("data") or {}).get(code) or {}).get("data") or {}
    day_raw = str(node.get("date") or "")
    if len(day_raw) != 8:
        return []
    day = f"{day_raw[0:4]}-{day_raw[4:6]}-{day_raw[6:8]}"
    if keep_date and day != keep_date:
        return []
    prev = None
    rows = []
    for item in node.get("data") or []:
        parts = str(item).split()
        if len(parts) < 2 or len(parts[0]) < 4:
            continue
        hhmm = parts[0]
        price = _num(parts[1])
        cum = _num(parts[2]) if len(parts) > 2 else None
        if cum is None or prev is None or cum < prev:
            vol = cum
        else:
            vol = cum - prev
        if cum is not None:
            prev = cum
        ts = f"{day} {hhmm[0:2]}:{hhmm[2:4]}:00+08"
        rows.append((ts, code, price, price, price, price, vol))
    return rows


def _write(conn, rows: list) -> int:
    if not rows:
        return 0
    sql = """
        INSERT INTO stock_minute (ts, code, freq, price, open, high, low, vol, source)
        VALUES %s
        ON CONFLICT (ts, code, freq) DO UPDATE SET
            price=EXCLUDED.price, open=EXCLUDED.open, high=EXCLUDED.high,
            low=EXCLUDED.low, vol=EXCLUDED.vol, ingest_ts=now()
    """
    with conn.cursor() as cur:
        execute_values(
            cur, sql, rows,
            template="(%s,%s,'1m',%s,%s,%s,%s,%s,'tencent')",
            page_size=2000,
        )
    conn.commit()
    return len(rows)


def _num(v):
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return None if n != n else n
