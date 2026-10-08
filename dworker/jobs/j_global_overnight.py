"""
j_global_overnight - 全球品种隔夜数据
目标表：global_daily
可用数据源（已验证）：
  美股: us.DJI(道琼斯), us.INX(标普500), us.IXIC(纳斯达克)
  港股: hkHSI(恒生指数)
  商品: hf_GC(黄金), hf_SI(白银), hf_CL(WTI原油)
源链：tencent → mootdx → eastmoney
注：tencent qt API 对欧股/日韩/外汇/VIX/加密覆盖有限，后续补充
"""
import json
import logging
import time
from datetime import datetime

logger = logging.getLogger(__name__)

# Verified working tencent qt codes
# Format: (qt_code, standard_code, market, name, parse_type)
# parse_type: "tilde" for ~-separated, "comma" for ,-separated
GLOBAL_VARIETIES = [
    # US indices (tilde format)
    ("us.DJI", "DJI", "US", "道琼斯", "tilde"),
    ("us.INX", "SPX", "US", "标普500", "tilde"),
    ("us.IXIC", "IXIC", "US", "纳斯达克", "tilde"),
    # HK (tilde format)
    ("hkHSI", "HSI", "HK", "恒生指数", "tilde"),
    # Commodities (comma format)
    ("hf_GC", "GC", "COMMODITY", "黄金", "comma"),
    ("hf_SI", "SI", "COMMODITY", "白银", "comma"),
    ("hf_CL", "CL", "COMMODITY", "WTI原油", "comma"),
]


def run(job_ctx, deg_chain, source_chain, conn, ingest_logger, raw_archiver, trigger="scheduled"):
    """Execute j_global_overnight."""
    t0 = time.time()
    today = datetime.now().strftime("%Y-%m-%d")

    all_rows = []
    source_used = None

    for source_name in source_chain:
        try:
            rows = _fetch_from_source(source_name)
            if rows and len(rows) >= 3:
                all_rows = rows
                source_used = source_name
                logger.info(f"[j_global_overnight] Got {len(rows)} rows from {source_name}")
                break
        except Exception as e:
            logger.warning(f"[j_global_overnight] Source {source_name} failed: {e}")
            continue

    if not all_rows:
        return {
            "success": False, "source_used": "none",
            "rows_in": 0, "rows_written": 0, "rows_quarantined": 0,
            "note": "all sources failed"
        }

    # Archive raw
    try:
        raw_archiver.archive("D7", "j_global_overnight", source_used, all_rows)
    except Exception as e:
        logger.warning(f"[j_global_overnight] Archive failed: {e}")

    # Write to DB
    rows_written = _write_to_db(conn, all_rows, source_used, today)

    return {
        "success": rows_written > 0,
        "source_used": source_used,
        "rows_in": len(all_rows),
        "rows_written": rows_written,
        "rows_quarantined": 0,
        "note": f"date={today} varieties={len(all_rows)} sources_tried={source_chain}"
    }


def _fetch_from_source(source_name: str) -> list:
    if source_name == "tencent":
        return _fetch_tencent()
    elif source_name == "eastmoney":
        return _fetch_eastmoney()
    elif source_name == "sina":
        return _fetch_sina()
    return []


def _fetch_tencent() -> list:
    """Fetch global data from Tencent qt API."""
    import requests
    rows = []
    today = datetime.now().strftime("%Y-%m-%d")
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    # Batch query all codes
    codes = [v[0] for v in GLOBAL_VARIETIES]
    code_map = {v[0]: v for v in GLOBAL_VARIETIES}

    query = ",".join(codes)
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
                    if not val_str or val_str == "1":
                        continue

                    info = code_map.get(qt_code)
                    if not info:
                        continue
                    _, std_code, market, name, parse_type = info

                    row = None
                    if parse_type == "tilde":
                        row = _parse_tilde_format(val_str, std_code, market, name, today)
                    elif parse_type == "comma":
                        row = _parse_comma_format(val_str, std_code, market, name, today)

                    if row:
                        rows.append(row)
                except Exception as e:
                    logger.debug(f"Parse qt line failed: {e}")
    except Exception as e:
        logger.warning(f"Tencent global fetch failed: {e}")

    return rows


def _parse_tilde_format(val_str: str, code: str, market: str, name: str, today: str) -> dict:
    """Parse tilde-separated format (US/HK indices)."""
    parts = val_str.split("~")
    if len(parts) < 35:
        return None

    close = _safe_float(parts[3])
    if not close or close <= 0:
        return None

    return {
        "date": today,
        "market": market,
        "code": code,
        "name": name,
        "close": close,
        "pct": _safe_float(parts[32]) if len(parts) > 32 else None,
        "open": _safe_float(parts[5]) if len(parts) > 5 else None,
        "high": _safe_float(parts[33]) if len(parts) > 33 else None,
        "low": _safe_float(parts[34]) if len(parts) > 34 else None,
        "volume": _safe_float(parts[6]) if len(parts) > 6 else None,
        "session": "close",
    }


def _parse_comma_format(val_str: str, code: str, market: str, name: str, today: str) -> dict:
    """Parse comma-separated format (commodities)."""
    parts = val_str.split(",")
    if len(parts) < 5:
        return None

    # Format: close,pct,open,high,...,date,name
    close = _safe_float(parts[0])
    if not close or close <= 0:
        return None

    return {
        "date": today,
        "market": market,
        "code": code,
        "name": parts[-1] if len(parts) > 12 else name,
        "close": close,
        "pct": _safe_float(parts[1]) if len(parts) > 1 else None,
        "open": _safe_float(parts[2]) if len(parts) > 2 else None,
        "high": _safe_float(parts[4]) if len(parts) > 4 else None,
        "low": _safe_float(parts[5]) if len(parts) > 5 else None,
        "session": "close",
    }


def _fetch_eastmoney() -> list:
    """Fallback: eastmoney (currently blocked from this server)."""
    return []


def _fetch_sina() -> list:
    """Fallback: Sina finance API."""
    return []


def _safe_float(val) -> float:
    if val is None or val == "" or val == "-":
        return None
    try:
        v = float(val)
        return v if v == v else None
    except (ValueError, TypeError):
        return None


def _write_to_db(conn, rows: list, source: str, today: str) -> int:
    """Write to global_daily. Returns count written."""
    if not rows:
        return 0

    count = 0
    with conn.cursor() as cur:
        for row in rows:
            try:
                cur.execute("""
                    INSERT INTO global_daily
                        (date, market, code, name, session, open, high, low,
                         close, pct, volume, amount, source)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (date, code, session) DO UPDATE SET
                        market = EXCLUDED.market,
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
                    row.get("date", today),
                    row.get("market"),
                    row.get("code"),
                    row.get("name"),
                    row.get("session", "close"),
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
                logger.warning(f"Write global_daily failed for {row.get('code')}: {e}")
    conn.commit()
    return count
