#!/usr/bin/env python3
"""补某一天缺失的个股资金流。东财日 K 资金流，只填库里还没有的代码。"""
from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import psycopg2
import requests
import yaml
from psycopg2.extras import execute_values

SECRETS = Path(__file__).resolve().parent.parent / "configs" / "secrets.yaml"
HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"}


def _secid(code: str) -> str | None:
    if code.startswith("sh"):
        return "1." + code[2:]
    if code.startswith("sz"):
        return "0." + code[2:]
    return None


def _fetch(code: str, day: str):
    secid = _secid(code)
    if not secid:
        return None
    try:
        resp = requests.get(
            "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get",
            params={
                "lmt": "30", "klt": "101", "secid": secid,
                "fields1": "f1,f2,f3,f7",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63",
            },
            headers=HEADERS, timeout=12,
        )
        lines = ((resp.json().get("data") or {}).get("klines") or [])
    except Exception:
        return None
    for line in lines:
        parts = str(line).split(",")
        if len(parts) < 13 or parts[0] != day:
            continue
        def num(i):
            try:
                return float(parts[i])
            except (TypeError, ValueError):
                return None
        return (
            day, code, num(1), num(6), num(5), num(4), num(3), num(2),
        )
    return None


def main():
    day = sys.argv[1] if len(sys.argv) > 1 else "2026-10-23"
    conf = yaml.safe_load(SECRETS.read_text())
    db = conf["database"]
    read = psycopg2.connect(
        host="127.0.0.1", port=15432, dbname="market_tsdb",
        user="duser_reader", password=db["duser_reader_password"],
    )
    with read.cursor() as cur:
        cur.execute("""
            SELECT d.code, d.name, d.close, d.pct
            FROM stock_daily d
            LEFT JOIN fund_flow_stock f ON f.date = d.date AND f.code = d.code
            WHERE d.date = %s AND f.code IS NULL
              AND (d.code LIKE 'sh%%' OR d.code LIKE 'sz%%')
        """, (day,))
        pending = cur.fetchall()
    read.close()
    print(f"missing {len(pending)}", flush=True)
    meta = {code: (name, close, pct) for code, name, close, pct in pending}
    found = []
    with ThreadPoolExecutor(max_workers=12) as pool:
        futs = {pool.submit(_fetch, code, day): code for code in meta}
        done = 0
        for fut in as_completed(futs):
            done += 1
            row = fut.result()
            if row:
                found.append(row)
            if done % 500 == 0:
                print(f"fetched {done}/{len(meta)} hit={len(found)}", flush=True)
    print(f"hit {len(found)}", flush=True)
    if not found:
        return
    write = psycopg2.connect(
        host="127.0.0.1", port=15432, dbname="market_tsdb",
        user="duser_writer", password=db["duser_writer_password"],
    )
    rows = []
    for date, code, main, main_pct, super_net, large, medium, small in found:
        name, close, pct = meta[code]
        rows.append((
            date, code, name, close, pct, main, main_pct,
            super_net, large, medium, small, "eastmoney-hist",
        ))
    sql = """
        INSERT INTO fund_flow_stock (
            date, code, name, close, pct,
            main_net_inflow, main_net_pct,
            super_large_net, large_net, medium_net, small_net, source
        ) VALUES %s
        ON CONFLICT (date, code) DO NOTHING
    """
    with write.cursor() as cur:
        execute_values(cur, sql, rows, page_size=1000)
    write.commit()
    write.close()
    print(f"written {len(rows)}", flush=True)


if __name__ == "__main__":
    main()
