"""宏观。新浪/akshare 的 CPI 只有月份，release_date 记成该月 1 日，不是统计局发布时刻。"""
import logging
import re
from datetime import datetime

logger = logging.getLogger(__name__)


def run(job_ctx, deg_chain, source_chain, conn, ingest_logger, raw_archiver, trigger="scheduled"):
    import akshare as ak

    frame = ak.macro_china_cpi()
    if frame is None or frame.empty:
        return {"success": False, "source_used": "akshare", "rows_in": 0,
                "rows_written": 0, "rows_quarantined": 0, "note": "MISS: CPI empty"}
    latest = frame.iloc[0]
    label = str(latest["月份"])
    match = re.match(r"(\d{4})年(\d{2})月份", label)
    if not match:
        return {"success": False, "source_used": "akshare", "rows_in": 1,
                "rows_written": 0, "rows_quarantined": 0, "note": f"MISS: bad month {label}"}
    period = f"{match.group(1)}-{match.group(2)}"
    release = f"{period}-01"
    row = {
        "release_date": release,
        "period": period,
        "indicator": "CPI",
        "value": float(latest["全国-当月"]),
        "yoy": float(latest["全国-同比增长"]),
        "mom": float(latest["全国-环比增长"]),
    }
    try:
        raw_archiver.archive("D8", "j_macro_indicators", "akshare", row)
    except Exception as e:
        logger.warning(f"[j_macro_indicators] archive {e}")
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO macro_indicators
                (release_date, period, indicator, country, value, yoy, mom, unit, source)
            VALUES (%s,%s,'CPI','CN',%s,%s,%s,'index/pct','akshare')
            ON CONFLICT (release_date, country, indicator, period) DO UPDATE SET
                value=EXCLUDED.value, yoy=EXCLUDED.yoy, mom=EXCLUDED.mom, ingest_ts=now()
        """, (row["release_date"], row["period"], row["value"], row["yoy"], row["mom"]))
    conn.commit()
    return {"success": True, "source_used": "akshare", "rows_in": 1, "rows_written": 1,
            "rows_quarantined": 0,
            "note": f"CPI {period} yoy={row['yoy']} mom={row['mom']} release_date={release} is month start"}
