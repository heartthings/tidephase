"""盘前期货报价。默认停用，梁总开市后才启用。腾讯 hf_ES 有报价，纳指期货这个代码没有。"""
import logging
from datetime import datetime

import requests

logger = logging.getLogger(__name__)
CODES = (("hf_ES", "ES", "标普500期货"),)


def run(job_ctx, deg_chain, source_chain, conn, ingest_logger, raw_archiver, trigger="scheduled"):
    rows = _fetch()
    if not rows:
        return {"success": False, "source_used": "tencent", "rows_in": 0,
                "rows_written": 0, "rows_quarantined": 0, "note": "MISS: no futures quote"}
    try:
        raw_archiver.archive("D7", "j_global_minute_pre", "tencent", rows)
    except Exception as e:
        logger.warning(f"[j_global_minute_pre] archive {e}")
    n = _write(conn, rows)
    return {"success": n > 0, "source_used": "tencent",
            "rows_in": len(rows), "rows_written": n, "rows_quarantined": 0,
            "note": f"quotes={n} nq_unavailable"}


def _fetch() -> list:
    query = ",".join(c[0] for c in CODES)
    try:
        resp = requests.get(f"https://qt.gtimg.cn/q={query}",
                            headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        text = resp.content.decode("gbk", errors="replace")
    except Exception as e:
        logger.warning(f"[j_global_minute_pre] {e}")
        return []
    wanted = {c[0]: c for c in CODES}
    rows = []
    for line in text.split(";"):
        if "=" not in line:
            continue
        key, val = line.split("=", 1)
        info = wanted.get(key.strip().replace("v_", ""))
        parts = val.strip().strip('"').split(",")
        if not info or len(parts) < 14 or parts[0] in ("", "1"):
            continue
        price = _num(parts[0])
        if price is None:
            continue
        day = parts[12]
        clock = parts[6] if len(parts[6]) == 8 else "00:00:00"
        rows.append({
            "ts": f"{day} {clock}+08",
            "code": info[1],
            "price": price,
            "pct": _num(parts[1]),
            "session": "pre",
        })
    return rows


def _write(conn, rows: list) -> int:
    n = 0
    with conn.cursor() as cur:
        for r in rows:
            cur.execute("""
                INSERT INTO global_minute (ts, code, freq, price, pct, session, source)
                VALUES (%s,%s,'15m',%s,%s,%s,'tencent')
                ON CONFLICT (ts, code, freq) DO UPDATE SET
                    price=EXCLUDED.price, pct=EXCLUDED.pct, session=EXCLUDED.session, ingest_ts=now()
            """, (r["ts"], r["code"], r["price"], r["pct"], r["session"]))
            n += 1
    conn.commit()
    return n


def _num(v):
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return None if n != n else n
