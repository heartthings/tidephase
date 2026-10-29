#!/usr/bin/env python3
"""把 stock_daily.circ_mv / total_mv 从东财估值报表回填到训练窗口起点。

来源：RPT_VALUEANALYSIS_DET.NOTLIMITED_MARKETCAP_A / TOTAL_MARKET_CAP（元）
写入：stock_daily，单位与现网一致（亿）。只填空值，不覆盖已有数。
"""
from __future__ import annotations

import argparse
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import psycopg2
import requests
import yaml
from psycopg2.extras import execute_values

SECRETS = Path(__file__).resolve().parent.parent / "configs" / "secrets.yaml"
URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/"}
PAGE = 5000


def _conn(writer=False):
    sec = yaml.safe_load(SECRETS.read_text())
    key = "duser_writer_password" if writer else "duser_reader_password"
    user = "duser_writer" if writer else "duser_reader"
    return psycopg2.connect(
        host="127.0.0.1", port=15432, dbname="market_tsdb",
        user=user, password=sec["database"][key],
    )


def _prefix(code: str) -> str:
    if code.startswith(("60", "68", "90")):
        return "sh" + code
    if code.startswith(("43", "83", "87", "92")):
        return "bj" + code
    return "sz" + code


def _trade_days(conn, start: date, end: date):
    """以 stock_daily 已有日期为准，保证训练窗口每一天都能回填。"""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT date FROM stock_daily
            WHERE date BETWEEN %s AND %s
            ORDER BY date
            """,
            (start, end),
        )
        days = [r[0] for r in cur.fetchall()]
        if days:
            return days
        cur.execute(
            """
            SELECT cal_date FROM trade_cal
            WHERE market='SSE' AND is_open=1
              AND cal_date BETWEEN %s AND %s
            ORDER BY cal_date
            """,
            (start, end),
        )
        return [r[0] for r in cur.fetchall()]


def _fetch_day(day: date) -> list[tuple]:
    rows = []
    page = 1
    while True:
        for attempt in range(3):
            try:
                resp = requests.get(
                    URL,
                    params={
                        "reportName": "RPT_VALUEANALYSIS_DET",
                        "columns": "SECURITY_CODE,TRADE_DATE,NOTLIMITED_MARKETCAP_A,TOTAL_MARKET_CAP",
                        "pageSize": PAGE,
                        "pageNumber": page,
                        "filter": f"(TRADE_DATE='{day.isoformat()}')",
                    },
                    headers=HEADERS,
                    timeout=40,
                )
                payload = resp.json()
                break
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(1.5 * (attempt + 1))
        data = ((payload.get("result") or {}).get("data") or [])
        if not data:
            break
        for item in data:
            code = str(item.get("SECURITY_CODE") or "").zfill(6)
            circ = item.get("NOTLIMITED_MARKETCAP_A")
            total = item.get("TOTAL_MARKET_CAP")
            if not code or circ is None:
                continue
            rows.append((
                day,
                _prefix(code),
                float(circ) / 1e8,
                None if total is None else float(total) / 1e8,
            ))
        pages = int((payload.get("result") or {}).get("pages") or page)
        if page >= pages:
            break
        page += 1
        time.sleep(0.25)
    return rows


def _write(conn, rows: list[tuple]) -> int:
    if not rows:
        return 0
    n = 0
    with conn.cursor() as cur:
        cur.execute("SET timescaledb.max_tuples_decompressed_per_dml_transaction = 0")
        for i in range(0, len(rows), 400):
            chunk = rows[i:i + 400]
            execute_values(
                cur,
                """
                UPDATE stock_daily AS s SET
                    circ_mv = COALESCE(s.circ_mv, v.circ_mv),
                    total_mv = COALESCE(NULLIF(s.total_mv, 0), v.total_mv, s.total_mv)
                FROM (VALUES %s) AS v(date, code, circ_mv, total_mv)
                WHERE s.date = v.date::date AND s.code = v.code
                  AND (s.circ_mv IS NULL OR s.circ_mv <= 0)
                """,
                chunk,
                template="(%s::date, %s, %s::float8, %s::float8)",
                page_size=400,
            )
            n += cur.rowcount
            conn.commit()
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2025-06-05")
    ap.add_argument("--end", default="2026-10-07")
    ap.add_argument("--sleep", type=float, default=0.35)
    args = ap.parse_args()
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)

    reader = _conn(False)
    writer = _conn(True)
    try:
        days = _trade_days(reader, start, end)
        print(f"days={len(days)} range={start}..{end}", flush=True)
        total = 0
        for i, day in enumerate(days, 1):
            rows = _fetch_day(day)
            n = _write(writer, rows)
            total += n
            print(f"[{i}/{len(days)}] {day} fetched={len(rows)} updated={n}", flush=True)
            time.sleep(args.sleep)
        print(f"done updated_rows={total}")
    finally:
        reader.close()
        writer.close()


if __name__ == "__main__":
    main()
