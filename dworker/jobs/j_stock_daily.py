"""
j_stock_daily - 全市场个股日线
目标表：stock_daily
策略：
  1. akshare stock_info_a_code_name() 获取全量代码（此接口可用）
  2. tencent qt.gtimg.cn 批量实时行情（此接口可用）
  3. 解析 ~ 分隔字段写入 stock_daily
源链：tencent → mootdx
"""
import json
import logging
import math
import time
from datetime import datetime

logger = logging.getLogger(__name__)

BATCH_SIZE = 60  # tencent batch query size


def run(job_ctx, deg_chain, source_chain, conn, ingest_logger, raw_archiver, trigger="scheduled"):
    """Execute j_stock_daily."""
    t0 = time.time()
    today = datetime.now().strftime("%Y-%m-%d")

    # Step 1: Get stock list
    stock_codes = _get_stock_list()
    if not stock_codes:
        return {
            "success": False, "source_used": "none",
            "rows_in": 0, "rows_written": 0, "rows_quarantined": 0,
            "note": "failed to get stock list"
        }
    logger.info(f"[j_stock_daily] Got {len(stock_codes)} stock codes")

    # Step 2: Batch fetch from tencent
    all_rows = []
    source_used = None

    for source_name in source_chain:
        if source_name == "tencent":
            all_rows = _fetch_tencent_batch(stock_codes, today)
            if all_rows:
                source_used = "tencent"
                break
        elif source_name == "mootdx":
            all_rows = _fetch_mootdx_batch(stock_codes, today)
            if all_rows:
                source_used = "mootdx"
                break

    if not all_rows:
        return {
            "success": False, "source_used": "none",
            "rows_in": 0, "rows_written": 0, "rows_quarantined": 0,
            "note": "all sources failed"
        }

    logger.info(f"[j_stock_daily] Fetched {len(all_rows)} rows from {source_used}")

    # Archive raw
    try:
        raw_archiver.archive("D2", "j_stock_daily", source_used, all_rows[:100])  # archive sample
    except Exception as e:
        logger.warning(f"[j_stock_daily] Archive failed: {e}")

    # Write to DB
    rows_written = _write_to_db(conn, all_rows, source_used, today)

    return {
        "success": rows_written > 0,
        "source_used": source_used,
        "rows_in": len(all_rows),
        "rows_written": rows_written,
        "rows_quarantined": 0,
        "note": f"date={today} source={source_used} total={len(all_rows)} written={rows_written}"
    }


def _get_stock_list() -> list:
    """Get all A-share stock codes with sh/sz prefix."""
    codes = []
    try:
        import akshare as ak
        df = ak.stock_info_a_code_name()
        if df is not None and not df.empty:
            for _, row in df.iterrows():
                raw_code = str(row.get("code", ""))
                std_code = _to_standard_code(raw_code)
                if std_code:
                    codes.append(std_code)
    except Exception as e:
        logger.warning(f"akshare stock list failed: {e}")

    return codes


def _fetch_tencent_batch(codes: list, today: str) -> list:
    """Fetch stock data from tencent qt API in batches."""
    import requests
    rows = []
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    total_batches = math.ceil(len(codes) / BATCH_SIZE)
    for batch_idx in range(total_batches):
        start = batch_idx * BATCH_SIZE
        end = start + BATCH_SIZE
        batch_codes = codes[start:end]

        query = ",".join(batch_codes)
        try:
            resp = session.get(f"https://qt.gtimg.cn/q={query}", timeout=15)
            if resp.status_code == 200:
                lines = resp.text.strip().split(";")
                for line in lines:
                    line = line.strip()
                    if not line or "=" not in line:
                        continue
                    try:
                        key_part, val_part = line.split("=", 1)
                        qt_code = key_part.replace("v_", "").strip()
                        val_str = val_part.strip().strip('"').strip("'")
                        if not val_str or len(val_str) < 10:
                            continue

                        parts = val_str.split("~")
                        if len(parts) < 45:
                            continue

                        name = parts[1]
                        close = _safe_float(parts[3])
                        if close <= 0:
                            continue

                        row = {
                            "date": today,
                            "code": qt_code,
                            "name": name,
                            "open": _safe_float(parts[5]),
                            "high": _safe_float(parts[33]) if len(parts) > 33 else 0,
                            "low": _safe_float(parts[34]) if len(parts) > 34 else 0,
                            "close": close,
                            "pct": _safe_float(parts[32]) if len(parts) > 32 else 0,
                            "volume": _safe_float(parts[6]) if len(parts) > 6 else 0,
                            "amount": _safe_float(parts[37]) if len(parts) > 37 else 0,
                            "turnover_rate": _safe_float(parts[38]) if len(parts) > 38 else 0,
                            "pe_ttm": _safe_float(parts[39]) if len(parts) > 39 else 0,
                            "total_mv": _safe_float(parts[45]) if len(parts) > 45 else 0,
                            "circ_mv": _safe_float(parts[44]) if len(parts) > 44 else 0,
                        }
                        rows.append(row)
                    except Exception as e:
                        logger.debug(f"Parse qt line failed: {e}")

            if (batch_idx + 1) % 20 == 0:
                logger.info(f"[j_stock_daily] Batch {batch_idx + 1}/{total_batches}, rows so far: {len(rows)}")

        except Exception as e:
            logger.warning(f"Tencent batch {batch_idx} failed: {e}")

    return rows


def _fetch_mootdx_batch(codes: list, today: str) -> list:
    """Fallback: fetch from mootdx (slow, per-stock)."""
    rows = []
    try:
        from mootdx.quotes import Quotes
        api = Quotes.factory(market='std')
        # Only fetch first 100 as fallback
        for code in codes[:100]:
            try:
                symbol = code[2:]
                market = 1 if code.startswith("sh") else 0
                data = api.bars(category=9, market=market, code=symbol, count=1)
                if data is not None and not data.empty:
                    row = data.iloc[-1]
                    rows.append({
                        "date": str(row.get("datetime", ""))[:10],
                        "code": code,
                        "name": "",
                        "open": float(row.get("open", 0)),
                        "high": float(row.get("high", 0)),
                        "low": float(row.get("low", 0)),
                        "close": float(row.get("close", 0)),
                        "volume": float(row.get("vol", 0)),
                        "amount": float(row.get("amount", 0)),
                    })
            except Exception:
                pass
    except ImportError:
        pass
    return rows


def _to_standard_code(raw_code: str) -> str:
    """Convert 600519 → sh600519, 000001 → sz000001"""
    raw_code = raw_code.strip()
    if len(raw_code) == 6 and raw_code.isdigit():
        if raw_code.startswith("6"):
            return f"sh{raw_code}"
        elif raw_code.startswith(("0", "3")):
            return f"sz{raw_code}"
        elif raw_code.startswith(("4", "8")):
            return f"bj{raw_code}"
    return ""


def _safe_float(val) -> float:
    if val is None or val == "" or val == "-":
        return 0.0
    try:
        v = float(val)
        return v if v == v else 0.0
    except (ValueError, TypeError):
        return 0.0


def _write_to_db(conn, rows: list, source: str, today: str) -> int:
    """Batch write to stock_daily. Returns count written."""
    if not rows:
        return 0

    count = 0
    batch_size = 500
    with conn.cursor() as cur:
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i + batch_size]
            for row in batch:
                try:
                    cur.execute("""
                        INSERT INTO stock_daily
                            (date, code, name, open, high, low, close, pct,
                             volume, amount, turnover_rate, total_mv, circ_mv,
                             pe_ttm, source)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (date, code) DO UPDATE SET
                            name = EXCLUDED.name,
                            open = EXCLUDED.open, high = EXCLUDED.high,
                            low = EXCLUDED.low, close = EXCLUDED.close,
                            pct = EXCLUDED.pct, volume = EXCLUDED.volume,
                            amount = EXCLUDED.amount,
                            turnover_rate = EXCLUDED.turnover_rate,
                            total_mv = EXCLUDED.total_mv,
                            circ_mv = EXCLUDED.circ_mv,
                            pe_ttm = EXCLUDED.pe_ttm,
                            source = EXCLUDED.source,
                            ingest_ts = now()
                    """, (
                        row["date"], row["code"], row.get("name"),
                        row.get("open", 0), row.get("high", 0),
                        row.get("low", 0), row["close"],
                        row.get("pct", 0), row.get("volume", 0),
                        row.get("amount", 0), row.get("turnover_rate", 0),
                        row.get("total_mv", 0), row.get("circ_mv", 0),
                        row.get("pe_ttm", 0), source,
                    ))
                    count += 1
                except Exception as e:
                    logger.debug(f"Write stock_daily failed for {row.get('code')}: {e}")
            conn.commit()
            if (i // batch_size + 1) % 5 == 0:
                logger.info(f"[j_stock_daily] Written batch {i // batch_size + 1}: {count} rows so far")

    return count
