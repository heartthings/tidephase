"""
j_index_daily - 六大指数日K
目标表：index_daily
六大指数：sh000001(上证), sz399001(深证成指), sz399006(创业板指),
          sh000300(沪深300), sh000016(上证50), sh000688(科创50)
源链：mootdx → tencent → akshare → eastmoney
"""
import json
import logging
import time
from datetime import datetime

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
    """Fetch from Tencent ifzq API."""
    import requests
    import json
    rows = []
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    for code, name in INDEX_CODES:
        try:
            resp = session.get(
                "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
                params={"param": f"{code},day,,,5,qfq", "_var": "kline_dayqfq"},
                timeout=10
            )
            if resp.status_code == 200:
                # Response is JSONP: kline_dayqfq={...}
                text = resp.text.strip()
                if "=" in text:
                    text = text.split("=", 1)[1]
                data = json.loads(text)
                stock_data = data.get("data", {}).get(code, {})
                day_data = stock_data.get("day", stock_data.get("qfqday", []))
                for item in day_data:
                    if len(item) >= 6:
                        rows.append({
                            "date": item[0],
                            "code": code,
                            "name": name,
                            "open": float(item[1]),
                            "close": float(item[2]),
                            "high": float(item[3]),
                            "low": float(item[4]),
                            "volume": float(item[5]) if len(item) > 5 else 0,
                            "amount": 0,
                        })
        except Exception as e:
            logger.warning(f"Tencent index fetch failed for {code}: {e}")
    return rows


def _fetch_mootdx() -> list:
    """Fetch from mootdx."""
    rows = []
    try:
        from mootdx.quotes import Quotes
        api = Quotes.factory(market='std')
        for code, name in INDEX_CODES:
            try:
                symbol = code[2:]
                market = 1 if code.startswith("sh") else 0
                data = api.bars(category=9, market=market, code=symbol, count=5)
                if data is not None and not data.empty:
                    for _, row in data.iterrows():
                        rows.append({
                            "date": str(row.get("datetime", ""))[:10],
                            "code": code,
                            "name": name,
                            "open": float(row.get("open", 0)),
                            "close": float(row.get("close", 0)),
                            "high": float(row.get("high", 0)),
                            "low": float(row.get("low", 0)),
                            "volume": float(row.get("vol", 0)),
                            "amount": float(row.get("amount", 0)),
                        })
            except Exception as e:
                logger.warning(f"mootdx index failed for {code}: {e}")
    except ImportError:
        logger.warning("mootdx not installed")
    return rows


def _fetch_akshare() -> list:
    """Fetch from akshare."""
    rows = []
    try:
        import akshare as ak
        # Map codes to akshare index symbols
        code_map = {
            "sh000001": "000001",  # 上证指数
            "sz399001": "399001",  # 深证成指
            "sz399006": "399006",  # 创业板指
            "sh000300": "000300",  # 沪深300
            "sh000016": "000016",  # 上证50
            "sh000688": "000688",  # 科创50
        }
        for code, name in INDEX_CODES:
            try:
                idx = code_map.get(code, code[2:])
                df = ak.stock_zh_index_daily(symbol=f"sh{idx}" if code.startswith("sh") else f"sz{idx}")
                if df is not None and not df.empty:
                    latest = df.iloc[-1]
                    rows.append({
                        "date": str(latest.get("date", ""))[:10],
                        "code": code,
                        "name": name,
                        "open": float(latest.get("open", 0)),
                        "close": float(latest.get("close", 0)),
                        "high": float(latest.get("high", 0)),
                        "low": float(latest.get("low", 0)),
                        "volume": float(latest.get("volume", 0)),
                    })
            except Exception as e:
                logger.warning(f"akshare index failed for {code}: {e}")
    except ImportError:
        logger.warning("akshare not installed")
    return rows


def _fetch_eastmoney() -> list:
    """Fetch from eastmoney."""
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
                    parts = klines[-1].split(",")
                    if len(parts) >= 7:
                        rows.append({
                            "date": parts[0],
                            "code": code,
                            "name": name,
                            "open": float(parts[1]),
                            "close": float(parts[2]),
                            "high": float(parts[3]),
                            "low": float(parts[4]),
                            "volume": float(parts[5]),
                            "amount": float(parts[6]),
                        })
        except Exception as e:
            logger.warning(f"eastmoney index failed for {code}: {e}")
    return rows


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
                        amount = EXCLUDED.amount,
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
