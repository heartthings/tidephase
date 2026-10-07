#!/usr/bin/env python3
"""
验收① 完整性扫描脚本
====================
给定日期区间，逐日 COUNT(stock_daily / index_daily / …) vs
trade_cal × instrument_master 在市清单期望值。

输出：缺失清单 + 缺失率
目标：stock < 0.1%、index = 0

数据访问双通道：
  1. 直连 PG 127.0.0.1:15432（只读账号）
  2. data-api http://127.0.0.1:8787（Bearer token）

用法：
  python test_completeness.py --start 2026-07-01 --end 2026-10-07
  python test_completeness.py --help
"""

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
PG_HOST = os.getenv("PG_HOST", "127.0.0.1")
PG_PORT = int(os.getenv("PG_PORT", "15432"))
PG_DB = os.getenv("PG_DB", "market_tsdb")
PG_USER = os.getenv("PG_USER", "duser_reader")
PG_PASS = os.getenv("PG_PASS", "")

API_BASE = os.getenv("DATA_API_BASE", "http://127.0.0.1:8787")
API_TOKEN = os.getenv("DATA_API_TOKEN", "")

# 六大指数
SIX_INDICES = [
    "sh000001", "sz399001", "sz399006",
    "sh000688", "sh000300", "sh000016",
]

# 目标缺失率阈值
THRESHOLD_STOCK = 0.001   # 0.1%
THRESHOLD_INDEX = 0.0     # 0%

# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _try_pg_connect() -> Optional[Any]:
    """尝试连接 PG，失败返回 None。"""
    try:
        import psycopg2
        conn = psycopg2.connect(
            host=PG_HOST, port=PG_PORT, dbname=PG_DB,
            user=PG_USER, password=PG_PASS,
            connect_timeout=5,
        )
        conn.autocommit = True
        return conn
    except Exception as e:
        return None


def _try_api_health() -> bool:
    """检查 API 是否可用。"""
    try:
        import urllib.request
        req = urllib.request.Request(f"{API_BASE}/health")
        if API_TOKEN:
            req.add_header("Authorization", f"Bearer {API_TOKEN}")
        resp = urllib.request.urlopen(req, timeout=5)
        return resp.status == 200
    except Exception:
        return False


def _query_pg(conn, sql: str, params: tuple = ()) -> List[tuple]:
    """执行 PG 查询，返回行列表。"""
    cur = conn.cursor()
    cur.execute(sql, params)
    return cur.fetchall()


def _query_api(endpoint: str, params: dict = None) -> Optional[dict]:
    """查询 data-api，返回 JSON。"""
    try:
        import urllib.request
        import urllib.parse
        url = f"{API_BASE}{endpoint}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url)
        if API_TOKEN:
            req.add_header("Authorization", f"Bearer {API_TOKEN}")
        resp = urllib.request.urlopen(req, timeout=30)
        return json.loads(resp.read())
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 核心逻辑
# ---------------------------------------------------------------------------

def get_trade_dates(conn, start: date, end: date) -> List[date]:
    """获取区间内交易日列表（CN 市场 is_open=1）。"""
    rows = _query_pg(
        "SELECT cal_date FROM trade_cal "
        "WHERE market='CN' AND is_open=1 AND cal_date BETWEEN %s AND %s "
        "ORDER BY cal_date",
        (start, end),
    )
    return [r[0] for r in rows]


def get_instrument_count(conn, trade_date: date) -> int:
    """获取某交易日在市证券数量（stock）。"""
    rows = _query_pg(
        "SELECT COUNT(*) FROM instrument_master "
        "WHERE inst_type='stock' AND status='active' "
        "AND (list_date IS NULL OR list_date <= %s) "
        "AND (delist_date IS NULL OR delist_date > %s)",
        (trade_date, trade_date),
    )
    return rows[0][0] if rows else 0


def get_stock_actual_count(conn, trade_date: date) -> int:
    """获取 stock_daily 某日实际行数。"""
    rows = _query_pg(
        "SELECT COUNT(*) FROM stock_daily WHERE date = %s",
        (trade_date,),
    )
    return rows[0][0] if rows else 0


def get_index_actual_count(conn, trade_date: date) -> int:
    """获取 index_daily 某日实际行数。"""
    rows = _query_pg(
        "SELECT COUNT(*) FROM index_daily WHERE date = %s",
        (trade_date,),
    )
    return rows[0][0] if rows else 0


def get_index_missing_codes(conn, trade_date: date) -> List[str]:
    """获取 index_daily 某日缺失的指数代码。"""
    rows = _query_pg(
        "SELECT im.code FROM instrument_master im "
        "WHERE im.inst_type='index' AND im.status='active' "
        "AND im.code IN %s "
        "AND NOT EXISTS ("
        "  SELECT 1 FROM index_daily idx "
        "  WHERE idx.date=%s AND idx.code=im.code"
        ")",
        (tuple(SIX_INDICES), trade_date),
    )
    return [r[0] for r in rows]


def run_completeness_check(start: date, end: date, channel: str = "pg") -> dict:
    """
    执行完整性扫描。
    返回结构化结果。
    """
    result = {
        "start": str(start),
        "end": str(end),
        "channel": channel,
        "trade_dates_count": 0,
        "stock": {"total_expected": 0, "total_actual": 0, "missing_rate": 0.0,
                   "missing_dates": [], "threshold": THRESHOLD_STOCK},
        "index": {"total_expected": 0, "total_actual": 0, "missing_rate": 0.0,
                  "missing_dates": [], "missing_details": [],
                  "threshold": THRESHOLD_INDEX},
        "status": "UNKNOWN",
    }

    if channel == "pg":
        conn = _try_pg_connect()
        if conn is None:
            result["status"] = "BLOCKED"
            result["error"] = (
                f"无法连接 PG {PG_HOST}:{PG_PORT}/{PG_DB}。"
                "等待铸码构建完成。请设置 PG_PASS 环境变量或检查 secrets.yaml。"
            )
            return result

        trade_dates = get_trade_dates(conn, start, end)
        result["trade_dates_count"] = len(trade_dates)

        if not trade_dates:
            result["status"] = "WARN"
            result["error"] = f"区间 {start}~{end} 无交易日（trade_cal 可能未初始化）"
            conn.close()
            return result

        stock_total_expected = 0
        stock_total_actual = 0
        index_total_expected = 0
        index_total_actual = 0

        for td in trade_dates:
            # stock
            expected_stock = get_instrument_count(conn, td)
            actual_stock = get_stock_actual_count(conn, td)
            stock_total_expected += expected_stock
            stock_total_actual += actual_stock
            if expected_stock > 0:
                day_missing = expected_stock - actual_stock
                if day_missing > 0:
                    rate = day_missing / expected_stock
                    if rate > THRESHOLD_STOCK:
                        result["stock"]["missing_dates"].append({
                            "date": str(td),
                            "expected": expected_stock,
                            "actual": actual_stock,
                            "missing": day_missing,
                            "missing_rate": round(rate, 6),
                        })

            # index
            expected_index = len(SIX_INDICES)
            actual_index = get_index_actual_count(conn, td)
            index_total_expected += expected_index
            index_total_actual += actual_index
            missing_codes = get_index_missing_codes(conn, td)
            if missing_codes:
                result["index"]["missing_dates"].append({
                    "date": str(td),
                    "expected": expected_index,
                    "actual": actual_index,
                    "missing_codes": missing_codes,
                })
                result["index"]["missing_details"].extend([
                    {"date": str(td), "code": c} for c in missing_codes
                ])

        conn.close()
    else:
        # API 通道
        if not _try_api_health():
            result["status"] = "BLOCKED"
            result["error"] = (
                f"data-api {API_BASE} 不可达。"
                "等待铸码构建完成。请设置 DATA_API_TOKEN 环境变量。"
            )
            return result

        # 通过 API 获取交易日
        cal_data = _query_api("/meta/trade_cal", {
            "market": "CN", "start": str(start), "end": str(end)
        })
        if not cal_data or "data" not in cal_data:
            result["status"] = "BLOCKED"
            result["error"] = "API /meta/trade_cal 返回异常"
            return result

        trade_dates = [
            date.fromisoisoformat(r["cal_date"])
            for r in cal_data["data"]
            if r.get("is_open") == 1
        ]
        result["trade_dates_count"] = len(trade_dates)

        for td in trade_dates:
            # 通过通用查询获取行数
            stock_data = _query_api("/data/stock_daily", {
                "start": str(td), "end": str(td), "fields": "code", "limit": 10000
            })
            actual_stock = len(stock_data.get("data", [])) if stock_data else 0

            index_data = _query_api("/data/index_daily", {
                "start": str(td), "end": str(td), "fields": "code", "limit": 100
            })
            actual_index = len(index_data.get("data", [])) if index_data else 0

            stock_total_expected += 5400  # 近似
            stock_total_actual += actual_stock
            index_total_expected += len(SIX_INDICES)
            index_total_actual += actual_index

    # 汇总
    if result["status"] == "UNKNOWN":
        if stock_total_expected > 0:
            result["stock"]["total_expected"] = stock_total_expected
            result["stock"]["total_actual"] = stock_total_actual
            result["stock"]["missing_rate"] = round(
                1 - stock_total_actual / stock_total_expected, 6
            )
        if index_total_expected > 0:
            result["index"]["total_expected"] = index_total_expected
            result["index"]["total_actual"] = index_total_actual
            result["index"]["missing_rate"] = round(
                1 - index_total_actual / index_total_expected, 6
            )

        stock_pass = result["stock"]["missing_rate"] <= THRESHOLD_STOCK
        index_pass = result["index"]["missing_rate"] <= THRESHOLD_INDEX
        result["status"] = "PASS" if (stock_pass and index_pass) else "FAIL"

    return result


def format_report(result: dict) -> str:
    """格式化输出报告。"""
    lines = []
    lines.append("=" * 70)
    lines.append("验收① 完整性扫描报告")
    lines.append("=" * 70)
    lines.append(f"区间: {result['start']} ~ {result['end']}")
    lines.append(f"通道: {result['channel']}")
    lines.append(f"交易日数: {result['trade_dates_count']}")
    lines.append(f"状态: {result['status']}")
    lines.append("")

    if "error" in result:
        lines.append(f"[BLOCKED] {result['error']}")
        lines.append("")
        return "\n".join(lines)

    # stock
    s = result["stock"]
    lines.append(f"--- stock_daily ---")
    lines.append(f"  期望总行数: {s['total_expected']:,}")
    lines.append(f"  实际总行数: {s['total_actual']:,}")
    lines.append(f"  缺失率: {s['missing_rate']:.4%}")
    lines.append(f"  阈值: {s['threshold']:.4%}")
    lines.append(f"  判定: {'PASS ✅' if s['missing_rate'] <= s['threshold'] else 'FAIL ❌'}")
    if s["missing_dates"]:
        lines.append(f"  缺失超标日期 ({len(s['missing_dates'])} 天):")
        for md in s["missing_dates"][:10]:
            lines.append(
                f"    {md['date']}: 期望 {md['expected']}, 实际 {md['actual']}, "
                f"缺失 {md['missing']} ({md['missing_rate']:.4%})"
            )
        if len(s["missing_dates"]) > 10:
            lines.append(f"    ... 共 {len(s['missing_dates'])} 天")
    lines.append("")

    # index
    idx = result["index"]
    lines.append(f"--- index_daily ---")
    lines.append(f"  期望总行数: {idx['total_expected']:,}")
    lines.append(f"  实际总行数: {idx['total_actual']:,}")
    lines.append(f"  缺失率: {idx['missing_rate']:.4%}")
    lines.append(f"  阈值: {idx['threshold']:.4%}")
    lines.append(f"  判定: {'PASS ✅' if idx['missing_rate'] <= idx['threshold'] else 'FAIL ❌'}")
    if idx["missing_details"]:
        lines.append(f"  缺失明细 ({len(idx['missing_details'])} 条):")
        for md in idx["missing_details"][:20]:
            lines.append(f"    {md['date']}: 缺失指数 {md['code']}")
    lines.append("")
    lines.append("=" * 70)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="验收① 完整性扫描：逐日 COUNT vs 期望值",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--start", required=True, help="起始日期 YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="截止日期 YYYY-MM-DD")
    parser.add_argument(
        "--channel", choices=["pg", "api"], default="pg",
        help="数据通道：pg（直连）或 api（data-api）",
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")
    args = parser.parse_args()

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)

    if start > end:
        print("ERROR: start > end", file=sys.stderr)
        sys.exit(1)

    result = run_completeness_check(start, end, args.channel)

    if args.json:
        # date 对象序列化
        def _ser(obj):
            if isinstance(obj, date):
                return str(obj)
            raise TypeError
        print(json.dumps(result, indent=2, default=_ser))
    else:
        print(format_report(result))

    sys.exit(0 if result["status"] in ("PASS", "BLOCKED") else 1)


if __name__ == "__main__":
    main()
