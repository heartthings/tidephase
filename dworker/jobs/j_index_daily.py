"""
j_index_daily - 六大指数日K
目标表：index_daily
六大指数：sh000001(上证), sz399001(深证成指), sz399006(创业板指),
          sh000300(沪深300), sh000016(上证50), sh000688(科创50)
源链：mootdx → tencent → akshare → eastmoney

门禁：trade_cal.is_open=0 时 SKIP，禁止落库（Z7 修复）。
"""
import json
import logging
import time
from datetime import datetime

from dworker.core.calendar_gate import check_trade_gate

logger = logging.getLogger(__name__)

INDEX_CODES = [
    ("sh000001", "上证指数"),
    ("sz399001", "深证成指"),
    ("sz399006", "创业板指"),
    ("sh000300", "沪深300"),
    ("sh000016", "上证50"),
    ("sh000688", "科创50"),
]


def run(job_ctx, deg_chain, source_chain, conn, ingest_logger, raw_archiver, trigger="scheduled"):
    """Execute j_index_daily."""
    t0 = time.time()
    today = datetime.now().strftime("%Y-%m-%d")

    try:
        filled = fill_index_amounts(conn)
        if filled:
            logger.info(f"[j_index_daily] filled zero amounts: {filled}")
    except Exception as e:
        logger.warning(f"[j_index_daily] amount fill failed: {e}")

    # ── 日历门禁：休市/非交易日不写业务表 ──
    gate = check_trade_gate(conn, market="SSE", check_date=today)
    if not gate["allowed"]:
        note = f"SKIP: {gate['reason']}"
        logger.info(f"[j_index_daily] {note}")
        try:
            ingest_logger.log_run(
                "j_index_daily", "D1", "index_daily", "none", "SKIP",
                rows_in=0, rows_written=0, rows_quarantined=0,
                note=note, trigger=trigger,
            )
        except Exception as e:
            logger.warning(f"[j_index_daily] ingest_log SKIP failed: {e}")
        return {
            "success": True, "source_used": "none",
            "rows_in": 0, "rows_written": 0, "rows_quarantined": 0,
            "note": note,
        }

    all_rows = []
    source_used = None

    # Try each source in chain
    for source_name in source_chain:
        try:
            rows = _fetch_from_source(source_name, job_ctx)
            if rows:
                all_rows = rows
                source_used = source_name
                logger.info(f"[j_index_daily] Got {len(rows)} rows from {source_name}")
                break
        except Exception as e:
            logger.warning(f"[j_index_daily] Source {source_name} failed: {e}")
            continue

    if not all_rows:
        return {
            "success": False, "source_used": "none",
            "rows_in": 0, "rows_written": 0, "rows_quarantined": 0,
            "note": "all sources failed"
        }

    # Filter to today's data only
    today_rows = [r for r in all_rows if str(r.get("date", ""))[:10] == today]
    if not today_rows:
        # If no today data, take the latest date
        dates = set(str(r.get("date", ""))[:10] for r in all_rows)
        latest = max(dates) if dates else today
        today_rows = [r for r in all_rows if str(r.get("date", ""))[:10] == latest]
        logger.warning(f"[j_index_daily] No data for {today}, using {latest}")

    # Archive raw
    try:
        raw_archiver.archive("D1", "j_index_daily", source_used or "unknown", today_rows)
    except Exception as e:
        logger.warning(f"[j_index_daily] Archive failed: {e}")

    # Write to DB
    rows_written = _write_to_db(conn, today_rows, source_used or "unknown")

    return {
        "success": rows_written > 0,
        "source_used": source_used,
        "rows_in": len(today_rows),
        "rows_written": rows_written,
        "rows_quarantined": 0,
        "note": f"date={today_rows[0].get('date', '?') if today_rows else '?'} codes={len(today_rows)}"
    }


def _fetch_from_source(source_name: str, job_ctx) -> list:
    """Fetch index data from a specific source."""
    if source_name == "tencent":
        return _fetch_tencent()
    elif source_name == "mootdx":
        return _fetch_mootdx()
    elif source_name == "akshare":
        return _fetch_akshare()
    elif source_name == "eastmoney":
        return _fetch_eastmoney()
    return []


def _fetch_tencent() -> list:
    """Fetch from Tencent ifzq API.
    B1 修复(2026-10-10): 计算 pct = (close - prev_close) / prev_close * 100。
    请求 10 天数据以确保最后一天有前收可算。
    """
    import requests
    import json
    rows = []
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    for code, name in INDEX_CODES:
        try:
            # B1: 请求 10 天（多取几天以确保有 prev_close）
            resp = session.get(
                "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
                params={"param": f"{code},day,,,10,qfq", "_var": "kline_dayqfq"},
                timeout=10
            )
            if resp.status_code == 200:
                text = resp.text.strip()
                if "=" in text:
                    text = text.split("=", 1)[1]
                data = json.loads(text)
                stock_data = data.get("data", {}).get(code, {})
                day_data = stock_data.get("day", stock_data.get("qfqday", []))
                prev_close = None
                for item in day_data:
                    if len(item) >= 6:
                        close = float(item[2])
                        pct = None
                        if prev_close and prev_close > 0:
                            pct = round((close - prev_close) / prev_close * 100, 4)
                        rows.append({
                            "date": item[0],
                            "code": code,
                            "name": name,
                            "open": float(item[1]),
                            "close": close,
                            "high": float(item[3]),
                            "low": float(item[4]),
                            "volume": float(item[5]) if len(item) > 5 else 0,
                            "amount": None,
                            "pct": pct,
                        })
                        prev_close = close
        except Exception as e:
            logger.warning(f"Tencent index fetch failed for {code}: {e}")
    return rows


def _fetch_mootdx() -> list:
    """Fetch from mootdx.
    B1 修复: 计算 pct。mootdx 返回的列可能包含 pctChange，否则手算。
    """
    rows = []
    try:
        from mootdx.quotes import Quotes
        api = Quotes.factory(market='std')
        for code, name in INDEX_CODES:
            try:
                symbol = code[2:]
                market = 1 if code.startswith("sh") else 0
                data = api.bars(category=9, market=market, code=symbol, count=10)
                if data is not None and not data.empty:
                    prev_close = None
                    for _, row in data.iterrows():
                        close = float(row.get("close", 0))
                        # mootdx 可能有 pctChange 列
                        pct_raw = row.get("pctChange") if "pctChange" in row.index else None
                        if pct_raw is not None and pct_raw == pct_raw:
                            pct = float(pct_raw)
                        elif prev_close and prev_close > 0:
                            pct = round((close - prev_close) / prev_close * 100, 4)
                        else:
                            pct = None
                        rows.append({
                            "date": str(row.get("datetime", ""))[:10],
                            "code": code,
                            "name": name,
                            "open": float(row.get("open", 0)),
                            "close": close,
                            "high": float(row.get("high", 0)),
                            "low": float(row.get("low", 0)),
                            "volume": float(row.get("vol", 0)),
                            "amount": float(row.get("amount", 0)),
                            "pct": pct,
                        })
                        prev_close = close
            except Exception as e:
                logger.warning(f"mootdx index failed for {code}: {e}")
    except ImportError:
        logger.warning("mootdx not installed")
    return rows


def _fetch_akshare() -> list:
    """Fetch from akshare.
    B1 修复: 取最后 10 行，计算 pct = (close - prev_close) / prev_close * 100。
    """
    rows = []
    try:
        import akshare as ak
        code_map = {
            "sh000001": "000001",
            "sz399001": "399001",
            "sz399006": "399006",
            "sh000300": "000300",
            "sh000016": "000016",
            "sh000688": "000688",
        }
        for code, name in INDEX_CODES:
            try:
                idx = code_map.get(code, code[2:])
                df = ak.stock_zh_index_daily(symbol=f"sh{idx}" if code.startswith("sh") else f"sz{idx}")
                if df is not None and not df.empty:
                    # B1: 取最后 10 行以计算 pct
                    tail = df.tail(10)
                    prev_close = None
                    for i, (_, row) in enumerate(tail.iterrows()):
                        close = float(row.get("close", 0))
                        pct = None
                        if prev_close and prev_close > 0:
                            pct = round((close - prev_close) / prev_close * 100, 4)
                        rows.append({
                            "date": str(row.get("date", ""))[:10],
                            "code": code,
                            "name": name,
                            "open": float(row.get("open", 0)),
                            "close": close,
                            "high": float(row.get("high", 0)),
                            "low": float(row.get("low", 0)),
                            "volume": float(row.get("volume", 0)),
                            "pct": pct,
                        })
                        prev_close = close
            except Exception as e:
                logger.warning(f"akshare index failed for {code}: {e}")
    except ImportError:
        logger.warning("akshare not installed")
    return rows


def _fetch_eastmoney() -> list:
    """Fetch from eastmoney.
    B1 修复: 取最后 10 根 K 线，计算 pct。
    """
    import requests
    rows = []
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://quote.eastmoney.com/"
    })

    for code, name in INDEX_CODES:
        try:
            secid = f"1.{code[2:]}" if code.startswith("sh") else f"0.{code[2:]}"
            resp = session.get(
                "https://push2his.eastmoney.com/api/qt/stock/kline/get",
                params={
                    "secid": secid, "fields1": "f1,f2,f3,f4,f5,f6",
                    "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
                    "klt": 101, "fqt": 1, "beg": "0", "end": "20500101",
                },
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                klines = data.get("data", {}).get("klines", [])
                if klines:
                    # B1: 取最后 10 根，计算 pct
                    tail = klines[-10:] if len(klines) >= 2 else klines
                    prev_close = None
                    for kline_str in tail:
                        parts = kline_str.split(",")
                        if len(parts) >= 7:
                            close = float(parts[2])
                            pct = None
                            if prev_close and prev_close > 0:
                                pct = round((close - prev_close) / prev_close * 100, 4)
                            rows.append({
                                "date": parts[0],
                                "code": code,
                                "name": name,
                                "open": float(parts[1]),
                                "close": close,
                                "high": float(parts[3]),
                                "low": float(parts[4]),
                                "volume": float(parts[5]),
                                "amount": float(parts[6]),
                                "pct": pct,
                            })
                            prev_close = close
        except Exception as e:
            logger.warning(f"eastmoney index failed for {code}: {e}")
    return rows


def fill_index_amounts(conn, bars: int = 30) -> int:
    """东财日 K 第 7 列是成交额。腾讯日 K 没有这一列，之前落成 0。只补 0 和空值。"""
    import requests
    updated = 0
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})
    with conn.cursor() as cur:
        for code, _name in INDEX_CODES:
            secid = ("1." if code.startswith("sh") else "0.") + code[2:]
            try:
                resp = session.get(
                    "https://push2his.eastmoney.com/api/qt/stock/kline/get",
                    params={
                        "secid": secid, "klt": 101, "fqt": 1, "lmt": bars,
                        "end": "20500101",
                        "fields1": "f1,f2,f3,f4,f5,f6",
                        "fields2": "f51,f52,f53,f54,f55,f56,f57",
                    },
                    timeout=15,
                )
                klines = ((resp.json().get("data") or {}).get("klines")) or []
            except Exception as e:
                logger.warning(f"[j_index_daily] amount {code}: {e}")
                continue
            for line in klines:
                parts = line.split(",")
                if len(parts) < 7:
                    continue
                try:
                    amount = float(parts[6])
                except ValueError:
                    continue
                if amount <= 0:
                    continue
                cur.execute("""
                    UPDATE index_daily
                    SET amount = %s, ingest_ts = now()
                    WHERE code = %s AND date = %s AND (amount IS NULL OR amount = 0)
                """, (amount, code, parts[0][:10]))
                updated += cur.rowcount
    conn.commit()
    return updated


def _write_to_db(conn, rows: list, source: str) -> int:
    """Write rows to index_daily table. Returns count written."""
    if not rows:
        return 0

    count = 0
    with conn.cursor() as cur:
        for row in rows:
            try:
                cur.execute("""
                    INSERT INTO index_daily (date, code, name, open, high, low, close,
                                             pct, volume, amount, source)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (date, code) DO UPDATE SET
                        name = EXCLUDED.name,
                        open = EXCLUDED.open,
                        high = EXCLUDED.high,
                        low = EXCLUDED.low,
                        close = EXCLUDED.close,
                        pct = EXCLUDED.pct,
                        volume = EXCLUDED.volume,
                        amount = COALESCE(NULLIF(EXCLUDED.amount, 0), index_daily.amount),
                        source = EXCLUDED.source,
                        ingest_ts = now()
                """, (
                    row.get("date"),
                    row.get("code"),
                    row.get("name"),
                    row.get("open"),
                    row.get("high"),
                    row.get("low"),
                    row.get("close"),
                    row.get("pct"),
                    row.get("volume"),
                    row.get("amount"),
                    source,
                ))
                count += 1
            except Exception as e:
                logger.warning(f"Write index_daily failed for {row.get('code')}: {e}")
    conn.commit()
    return count
