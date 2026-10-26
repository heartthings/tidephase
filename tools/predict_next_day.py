#!/usr/bin/env python3
"""次日首板/二板预测 CLI（数据层本地调试用；线上由 data-api /data/predict_limitup 提供）。

用法：
  python tools/predict_next_day.py --date 2026-10-23 --format markdown
  python tools/predict_next_day.py --date 2026-10-23 --format json
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data_api.predict_limitup import get_conn, predict, render_markdown


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="基准交易日 YYYY-MM-DD，默认最新日线日")
    ap.add_argument("--format", choices=["markdown", "json"], default="markdown")
    ap.add_argument("--top-first", type=int, default=15)
    ap.add_argument("--top-second", type=int, default=10)
    args = ap.parse_args()

    d = date.fromisoformat(args.date) if args.date else None
    conn = get_conn()
    try:
        result = predict(conn, d, args.top_first, args.top_second)
    finally:
        conn.close()

    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        print(render_markdown(result))


if __name__ == "__main__":
    main()
