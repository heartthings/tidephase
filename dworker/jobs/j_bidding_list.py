"""
j_bidding_list - 竞价列表（五维原料）
目标表：bidding_list
Q11 冻结 9 字段子集：jjzf, jjje, jjcje, jjhs, ztwme, twenty_ztwme, fd, zdfd, sjlt
源链：eastmoney
quotations_type: 1=09:15, 2=09:20, 3=09:25, 9=09:26终版
"""
import json
import logging
import time
from datetime import datetime

logger = logging.getLogger(__name__)


def run(job_ctx, deg_chain, source_chain, conn, ingest_logger, raw_archiver, trigger="scheduled"):
    """Execute j_bidding_list."""
    t0 = time.time()
    today = datetime.now().strftime("%Y-%m-%d")
    now = datetime.now()

    # Determine quotations_type based on current time
    hour_min = now.hour * 100 + now.minute
    if hour_min <= 915:
        quotations_type = 1
    elif hour_min <= 920:
        quotations_type = 2
    elif hour_min <= 925:
        quotations_type = 3
    else:
        quotations_type = 9  # final

    all_rows = []
    source_used = None

    for source_name in source_chain:
        try:
            rows = _fetch_from_source(source_name, today, quotations_type)
            if rows:
                all_rows = rows
                source_used = source_name
                logger.info(f"[j_bidding_list] Got {len(rows)} rows from {source_name}")
                break
        except Exception as e:
            logger.warning(f"[j_bidding_list] Source {source_name} failed: {e}")
            continue

    if not all_rows:
        return {
            "success": False, "source_used": "none",
            "rows_in": 0, "rows_written": 0, "rows_quarantined": 0,
            "note": f"all sources failed type={quotations_type}"
        }

    # Archive raw
    try:
        raw_archiver.archive("D3", "j_bidding_list", source_used, all_rows)
    except Exception as e:
        logger.warning(f"[j_bidding_list] Archive failed: {e}")

    # Write to DB
    rows_written = _write_to_db(conn, all_rows, source_used, today, quotations_type)

    return {
        "success": rows_written > 0,
        "source_used": source_used,
        "rows_in": len(all_rows),
        "rows_written": rows_written,
        "rows_quarantined": 0,
        "note": f"date={today} type={quotations_type} count={len(all_rows)}"
    }


def _fetch_from_source(source_name: str, today: str, quotations_type: int) -> list:
    if source_name == "eastmoney":
        return _fetch_eastmoney_bidding(today)
    return []


def _fetch_eastmoney_bidding(today: str) -> list:
    """Fetch bidding list from eastmoney push2 API."""
    import requests
    rows = []
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://quote.eastmoney.com/"
    })

    try:
        # Eastmoney bidding/auction data API
        resp = session.get(
            "https://push2.eastmoney.com/api/qt/clist/get",
            params={
                "pn": 1, "pz": 5000, "po": 1, "np": 1, "fltt": 2, "invt": 2,
                "fid": "f3",
                "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048",
                "fields": "f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f14,f15,f16,f17,f18,f20,f21"
            },
            timeout=30
        )
        if resp.status_code == 200:
            data = resp.json()
            items = data.get("data", {}).get("diff", [])
            for item in items:
                code_raw = str(item.get("f12", ""))
                code = _to_standard_code(code_raw)
                close = _safe_float(item.get("f2"))
                if close <= 0:
                    continue

                # Map to bidding_list fields
                # During bidding period, f2=latest price, f17=open, f3=pct
                rows.append({
                    "date": today,
                    "code": code,
                    "name": str(item.get("f14", "")),
                    "jjzf": _safe_float(item.get("f3")),  # 竞价涨幅%
                    "jjje": int(_safe_float(item.get("f6"))),  # 竞价金额
                    "jjcje": int(_safe_float(item.get("f20"))),  # 竞价成交额
                    "jjhs": _safe_float(item.get("f5")),  # 竞价换手
                    "ztwme": int(_safe_float(item.get("f21"))),  # 昨总市值
                    "twenty_ztwme": 0,  # 20日前的总市值（需额外计算）
                    "fd": int(_safe_float(item.get("f8"))),  # 放量
                    "zdfd": 0,  # 涨跌放量
                    "sjlt": 0,  # 实时流通
                    "ssbk": "",  # 所属板块
                    "ztsj": "",  # 涨停时间
                    "ztyy": "",  # 涨停原因
                    "bkztsl": 0,  # 板块涨停数量
                    "limit_up_status": "",  # 涨停状态
                    "quotations_type": 1,
                })
    except Exception as e:
        logger.warning(f"eastmoney bidding fetch failed: {e}")

    return rows


def _to_standard_code(raw_code: str) -> str:
    raw_code = raw_code.strip()
    if len(raw_code) == 6 and raw_code.isdigit():
        if raw_code.startswith("6"):
            return f"sh{raw_code}"
        elif raw_code.startswith(("0", "3")):
            return f"sz{raw_code}"
        elif raw_code.startswith(("4", "8")):
            return f"bj{raw_code}"
    return raw_code


def _safe_float(val) -> float:
    if val is None or val == "-" or val == "":
        return 0.0
    try:
        v = float(val)
        return v if v == v else 0.0
    except (ValueError, TypeError):
        return 0.0


def _write_to_db(conn, rows: list, source: str, today: str, quotations_type: int) -> int:
    """Write to bidding_list. Returns count written."""
    if not rows:
        return 0

    count = 0
    with conn.cursor() as cur:
        for row in rows:
            try:
                cur.execute("""
                    INSERT INTO bidding_list
                        (date, code, name, jjzf, jjje, jjcje, jjhs,
                         ztwme, twenty_ztwme, fd, zdfd, sjlt,
                         ssbk, ztsj, ztyy, bkztsl, limit_up_status,
                         quotations_type, source)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (date, code, quotations_type) DO UPDATE SET
                        name = EXCLUDED.name,
                        jjzf = EXCLUDED.jjzf, jjje = EXCLUDED.jjje,
                        jjcje = EXCLUDED.jjcje, jjhs = EXCLUDED.jjhs,
                        ztwme = EXCLUDED.ztwme, twenty_ztwme = EXCLUDED.twenty_ztwme,
                        fd = EXCLUDED.fd, zdfd = EXCLUDED.zdfd,
                        sjlt = EXCLUDED.sjlt,
                        ssbk = EXCLUDED.ssbk, ztsj = EXCLUDED.ztsj,
                        ztyy = EXCLUDED.ztyy, bkztsl = EXCLUDED.bkztsl,
                        limit_up_status = EXCLUDED.limit_up_status,
                        source = EXCLUDED.source,
                        ingest_ts = now()
                """, (
                    row["date"], row["code"], row.get("name"),
                    row.get("jjzf", 0), row.get("jjje", 0),
                    row.get("jjcje", 0), row.get("jjhs", 0),
                    row.get("ztwme", 0), row.get("twenty_ztwme", 0),
                    row.get("fd", 0), row.get("zdfd", 0),
                    row.get("sjlt", 0), row.get("ssbk", ""),
                    row.get("ztsj", ""), row.get("ztyy", ""),
                    row.get("bkztsl", 0), row.get("limit_up_status", ""),
                    quotations_type, source,
                ))
                count += 1
            except Exception as e:
                logger.debug(f"Write bidding_list failed for {row.get('code')}: {e}")
        conn.commit()
    return count
