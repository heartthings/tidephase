"""全市场个股 1 分钟线。

沪深：腾讯 mkline，最近 400 根（约一个半交易日），价和量。
成交额、分时均价来自新浪分钟 K。额是这一分钟的成交额，单位元。
均价是当日起从 09:30 累计的成交额 / 累计成交股数。采集机上腾讯分时被拦，不用。
北交所没有分钟 K，用腾讯分时；有累计额时同样落额和均价。
定时任务只落目标交易日。手工触发不带 date 时，把这次返回里的交易日都落上。
补历史额用新浪分钟 K（成交量仍以腾讯的手为准，不覆盖）。
"""
import json
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
    amount_rows = 0
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
        amount_rows += sum(1 for row in rows if row[7] is not None)
        if rows and not sample:
            sample = rows[:20]
        written += _write(conn, rows)
        logger.info(
            f"[j_stock_minute] {min(i + BATCH, len(codes))}/{len(codes)} "
            f"written={written} amount={amount_rows} empty={empty} errors={errors}"
        )

    if sample:
        try:
            raw_archiver.archive("D2", "j_stock_minute", "tencent", sample)
        except Exception as e:
            logger.warning(f"[j_stock_minute] archive {e}")

    note = (
        f"date={keep_date or 'window'} codes={len(codes)} bars={written} "
        f"amount={amount_rows} empty={empty} errors={errors} "
        f"days={','.join(sorted(dates)) or '-'}"
    )
    covered = len(codes) - errors
    amount_ok = True
    if keep_date and written > 1000 and amount_rows < int(written * 0.8):
        amount_ok = False
        note += " amount coverage below 80%"
    return {"success": written > 0 and errors < covered and amount_ok, "source_used": "tencent",
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
                rows = _apply_amounts(_fetch_mkline(code, keep_date), _fetch_trend_amounts(code, keep_date))
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


def _fetch_trend_amounts(code: str, keep_date):
    """新浪分钟 K。键是分钟时间，值是（这一分钟成交额元，累计均价元）。"""
    datalen = 320 if keep_date else 500
    rows, ok = _sina_amount_rows(code, datalen)
    if not ok:
        return {}
    out = {}
    for ts, _code, amount, avg in rows:
        if keep_date and not ts.startswith(keep_date):
            continue
        out[ts] = (amount, avg)
    return out


def _amounts_from_trend(node: dict, keep_date) -> dict:
    day_raw = str(node.get("date") or "")
    if len(day_raw) != 8:
        return {}
    day = f"{day_raw[0:4]}-{day_raw[4:6]}-{day_raw[6:8]}"
    if keep_date and day != keep_date:
        return {}
    prev_amt = None
    out = {}
    for item in node.get("data") or []:
        parts = str(item).split()
        if len(parts) < 4 or len(parts[0]) < 4:
            continue
        cum_vol = _num(parts[2])
        cum_amt = _num(parts[3])
        if cum_amt is None:
            continue
        if prev_amt is None or cum_amt < prev_amt:
            amount = cum_amt
        else:
            amount = cum_amt - prev_amt
        prev_amt = cum_amt
        avg = cum_amt / (cum_vol * 100) if cum_vol else None
        hhmm = parts[0]
        ts = f"{day} {hhmm[0:2]}:{hhmm[2:4]}:00+08"
        out[ts] = (amount, avg)
    return out


def _apply_amounts(rows: list, amounts: dict) -> list:
    applied = []
    for ts, code, price, open_, high, low, vol in rows:
        amount, avg = amounts.get(ts, (None, None))
        applied.append((ts, code, price, open_, high, low, vol, amount, avg))
    return applied


def _fetch_trend(code: str, keep_date) -> list:
    """北交所分时。开高低用现价。有累计额时同时落这一分钟的额和均价。"""
    url = f"https://web.ifzq.gtimg.cn/appstock/app/minute/query?code={code}"
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com/"}, timeout=20)
    node = ((resp.json().get("data") or {}).get(code) or {}).get("data") or {}
    day_raw = str(node.get("date") or "")
    if len(day_raw) != 8:
        return []
    day = f"{day_raw[0:4]}-{day_raw[4:6]}-{day_raw[6:8]}"
    if keep_date and day != keep_date:
        return []
    amounts = _amounts_from_trend(node, keep_date)
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
        amount, avg = amounts.get(ts, (None, None))
        rows.append((ts, code, price, price, price, price, vol, amount, avg))
    return rows


def _write(conn, rows: list) -> int:
    if not rows:
        return 0
    sql = """
        INSERT INTO stock_minute (ts, code, freq, price, open, high, low, vol, amount, avg_price, source)
        VALUES %s
        ON CONFLICT (ts, code, freq) DO UPDATE SET
            price=EXCLUDED.price, open=EXCLUDED.open, high=EXCLUDED.high,
            low=EXCLUDED.low, vol=EXCLUDED.vol,
            amount=COALESCE(EXCLUDED.amount, stock_minute.amount),
            avg_price=COALESCE(EXCLUDED.avg_price, stock_minute.avg_price),
            ingest_ts=now()
    """
    with conn.cursor() as cur:
        execute_values(
            cur, sql, rows,
            template="(%s,%s,'1m',%s,%s,%s,%s,%s,%s,%s,'tencent')",
            page_size=2000,
        )
    conn.commit()
    return len(rows)


def backfill_amount(conn, datalen=1600) -> dict:
    """新浪分钟 K 补已落库 bars 的成交额和分时均价。不改 vol。"""
    codes = _load_codes(conn)
    written = 0
    empty = 0
    errors = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for i, (rows, ok) in enumerate(pool.map(lambda c: _sina_amount_rows(c, datalen), codes), start=1):
            if not ok:
                errors += 1
            elif not rows:
                empty += 1
            else:
                written += _update_amounts(conn, rows)
            if i % 200 == 0 or i == len(codes):
                logger.info(
                    f"[j_stock_minute] backfill {i}/{len(codes)} "
                    f"updated={written} empty={empty} errors={errors}"
                )
                print(
                    f"[j_stock_minute] backfill {i}/{len(codes)} "
                    f"updated={written} empty={empty} errors={errors}",
                    flush=True,
                )
    return {"codes": len(codes), "updated": written, "empty": empty, "errors": errors}


def _sina_amount_rows(code: str, datalen: int):
    last = None
    for attempt in range(2):
        try:
            resp = requests.get(
                "https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20_x=/CN_MarketDataService.getKLineData",
                params={"symbol": code, "scale": 1, "ma": "no", "datalen": datalen},
                headers={"User-Agent": "Mozilla/5.0", "Referer": "https://quotes.sina.cn/"},
                timeout=20,
            )
            text = resp.text
            start, end = text.find("(["), text.rfind("])")
            if start < 0 or end < start:
                raise RuntimeError(f"sina minute payload unusable ({resp.status_code})")
            bars = json.loads(text[start + 1:end + 1])
            return _cumulative_avg(code, bars), True
        except Exception as e:
            last = e
            time.sleep(0.4)
    logger.warning(f"[j_stock_minute] sina amount {code}: {last}")
    return [], False


def _cumulative_avg(code: str, bars: list) -> list:
    """新浪 volume 是股。均价按每个交易日从 09:30 累计；窗口切在半路的那天不写均价。"""
    grouped = {}
    for item in bars:
        stamp = str(item.get("day") or "")
        amount = _num(item.get("amount"))
        if len(stamp) < 16 or amount is None:
            continue
        grouped.setdefault(stamp[:10], []).append((stamp, amount, _num(item.get("volume")) or 0.0))
    rows = []
    for day in sorted(grouped):
        items = sorted(grouped[day])
        full = items[0][0][11:16] <= "09:31"
        cum_amt = 0.0
        cum_vol = 0.0
        for stamp, amount, volume in items:
            cum_amt += amount
            cum_vol += volume
            avg = cum_amt / cum_vol if full and cum_vol else None
            rows.append((stamp[:16] + ":00+08", code, amount, avg))
    return rows


def _update_amounts(conn, rows: list) -> int:
    if not rows:
        return 0
    sql = """
        UPDATE stock_minute AS m SET
            amount = v.amount,
            avg_price = COALESCE(v.avg_price, m.avg_price),
            ingest_ts = now()
        FROM (VALUES %s) AS v(ts, code, amount, avg_price)
        WHERE m.ts = v.ts AND m.code = v.code AND m.freq = '1m'
    """
    with conn.cursor() as cur:
        execute_values(
            cur, sql, rows,
            template="(%s::timestamptz,%s,%s::float8,%s::float8)",
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
