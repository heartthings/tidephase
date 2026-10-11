"""双源复核。库内收盘对腾讯现价，写入 verify_source / verify_diff。相对差超过 1% 记 FAIL。"""
import logging

import requests

logger = logging.getLogger(__name__)


def run(job_ctx, deg_chain, source_chain, conn, ingest_logger, raw_archiver, trigger="scheduled"):
    with conn.cursor() as cur:
        cur.execute("SELECT max(date) FROM index_daily WHERE code = 'sh000001'")
        day = cur.fetchone()[0]
    if day is None:
        return {"success": False, "source_used": "tencent", "rows_in": 0,
                "rows_written": 0, "rows_quarantined": 0, "note": "MISS: index_daily empty"}
    samples = [("index_daily", "sh000001")]
    with conn.cursor() as cur:
        cur.execute("""
            SELECT code FROM stock_daily
            WHERE date = %s AND code ~ '^(sh6|sz0|sz3)'
            ORDER BY code
        """, (day,))
        samples += [("stock_daily", r[0]) for r in cur.fetchall()]
        cur.execute("SELECT code FROM etf_daily WHERE date = %s AND code = 'sh510300'", (day,))
        if cur.fetchone():
            samples.append(("etf_daily", "sh510300"))
    quotes = _quotes([c for _, c in samples])
    rows = []
    skipped = 0
    for table, code in samples:
        with conn.cursor() as cur:
            cur.execute(f"SELECT close FROM {table} WHERE date = %s AND code = %s", (day, code))
            found = cur.fetchone()
        live = quotes.get(code)
        if not found or live is None:
            skipped += 1
            continue
        db_close = float(found[0])
        if db_close == 0:
            skipped += 1
            continue
        diff_pct = abs(live - db_close) / db_close * 100
        rows.append((table, code, db_close, live, diff_pct))
    if not rows:
        return {"success": False, "source_used": "tencent", "rows_in": len(samples),
                "rows_written": 0, "rows_quarantined": 0, "note": "MISS: no comparable quotes"}
    _write(conn, day, rows)
    block = sum(1 for *_, d in rows if d > 1)
    warn = sum(1 for *_, d in rows if 0.35 < d <= 1)
    max_diff = max(d for *_, d in rows)
    ok = block == 0
    return {
        "success": ok, "source_used": "tencent",
        "rows_in": len(samples), "rows_written": len(rows), "rows_quarantined": block,
        "note": f"date={day} checked={len(rows)} skipped={skipped} warn={warn} block={block} max_diff_pct={max_diff:.4f}",
    }


def _quotes(codes: list) -> dict:
    out = {}
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})
    for i in range(0, len(codes), 60):
        try:
            resp = session.get("https://qt.gtimg.cn/q=" + ",".join(codes[i:i + 60]), timeout=20)
            text = resp.content.decode("gbk", errors="replace")
        except Exception as e:
            logger.warning(f"[j_verify_daily] {e}")
            continue
        for line in text.split(";"):
            if "=" not in line:
                continue
            key, val = line.split("=", 1)
            parts = val.strip().strip('"').split("~")
            if len(parts) < 4:
                continue
            try:
                out[key.strip().replace("v_", "")] = float(parts[3])
            except ValueError:
                continue
    return out


def _write(conn, day, rows):
    by_table = {}
    with conn.cursor() as cur:
        for table, code, db_close, live, diff_pct in rows:
            cur.execute("""
                INSERT INTO verify_source (
                    date, target_table, code, primary_source, primary_value,
                    verify_source, verify_value, diff_pct, source
                ) VALUES (%s,%s,%s,'db',%s,'tencent',%s,%s,'verify')
                ON CONFLICT (date, target_table, code, verify_source) DO UPDATE SET
                    primary_value=EXCLUDED.primary_value, verify_value=EXCLUDED.verify_value,
                    diff_pct=EXCLUDED.diff_pct, ingest_ts=now()
            """, (day, table, code, db_close, live, diff_pct))
            bucket = by_table.setdefault(table, [])
            bucket.append(diff_pct)
        for table, diffs in by_table.items():
            cur.execute("""
                INSERT INTO verify_diff (
                    date, target_table, total_rows, checked_rows, warn_count, block_count, max_diff_pct, source
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,'verify')
                ON CONFLICT (date, target_table) DO UPDATE SET
                    checked_rows=EXCLUDED.checked_rows, warn_count=EXCLUDED.warn_count,
                    block_count=EXCLUDED.block_count, max_diff_pct=EXCLUDED.max_diff_pct, ingest_ts=now()
            """, (
                day, table, len(diffs), len(diffs),
                sum(1 for d in diffs if 0.35 < d <= 1),
                sum(1 for d in diffs if d > 1),
                max(diffs),
            ))
    conn.commit()
