#!/usr/bin/env python3
"""
验收③ 时效性检查脚本
====================
读 ingest_log，验证 critical 作业 end_ts ≤ 硬截止时刻：
  - 收盘全量 16:30（Asia/Shanghai）
  - 隔夜全球 08:00（Asia/Shanghai）
连续 N 日统计。

用法：
  python test_timeliness.py --days 20
  python test_timeliness.py --help
"""

import argparse
import json
import os
import sys
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional

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

# 硬截止时刻（Asia/Shanghai）
DEADLINE_EVENING = time(16, 30)   # 收盘全量
DEADLINE_MORNING = time(8, 0)     # 隔夜全球

# critical 作业清单
CRITICAL_JOBS_EVENING = [
    "j_stock_daily",
    "j_index_daily",
    "j_zt_pools",
    "j_sentiment_calc",
    "j_stock_minute",
    "j_etf_daily",
]

CRITICAL_JOBS_MORNING = [
    "j_global_overnight",
]

# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _try_pg_connect() -> Optional[Any]:
    try:
        import psycopg2
        conn = psycopg2.connect(
            host=PG_HOST, port=PG_PORT, dbname=PG_DB,
            user=PG_USER, password=PG_PASS,
            connect_timeout=5,
        )
        conn.autocommit = True
        return conn
    except Exception:
        return None


def _query_pg(conn, sql: str, params: tuple = ()) -> List[tuple]:
    cur = conn.cursor()
    cur.execute(sql, params)
    return cur.fetchall()


# ---------------------------------------------------------------------------
# 核心逻辑
# ---------------------------------------------------------------------------

def run_timeliness_check(days: int, channel: str = "pg") -> dict:
    """执行时效性检查。"""
    result = {
        "days": days,
        "channel": channel,
        "evening": {
            "deadline": str(DEADLINE_EVENING),
            "jobs": CRITICAL_JOBS_EVENING,
            "stats": {},
            "violations": [],
        },
        "morning": {
            "deadline": str(DEADLINE_MORNING),
            "jobs": CRITICAL_JOBS_MORNING,
            "stats": {},
            "violations": [],
        },
        "status": "UNKNOWN",
    }

    if channel == "pg":
        conn = _try_pg_connect()
        if conn is None:
            result["status"] = "BLOCKED"
            result["error"] = (
                f"无法连接 PG {PG_HOST}:{PG_PORT}/{PG_DB}。"
                "等待铸码构建完成。"
            )
            return result

        # 查询最近 N 日的 ingest_log
        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        # 收盘全量作业时效
        for job in CRITICAL_JOBS_EVENING:
            rows = _query_pg(
                "SELECT ts AT TIME ZONE 'Asia/Shanghai' AS local_ts, "
                "       status, duration_ms, note "
                "FROM ingest_log "
                "WHERE job = %s AND ts::date BETWEEN %s AND %s "
                "ORDER BY ts DESC",
                (job, start_date, end_date),
            )

            job_stats = {
                "total_runs": len(rows),
                "on_time": 0,
                "late": 0,
                "fail": 0,
                "avg_duration_ms": 0,
            }

            durations = []
            for row in rows:
                local_ts = row[0]
                status = row[1]
                duration_ms = row[2]

                if status in ("FAIL", "MISS"):
                    job_stats["fail"] += 1
                    continue

                if local_ts is not None:
                    # 检查 end_ts（ts + duration）是否超截止
                    end_ts = local_ts
                    if duration_ms:
                        end_ts = local_ts + timedelta(milliseconds=duration_ms)

                    if end_ts.time() <= DEADLINE_EVENING:
                        job_stats["on_time"] += 1
                    else:
                        job_stats["late"] += 1
                        result["evening"]["violations"].append({
                            "date": str(local_ts.date()),
                            "job": job,
                            "end_ts": str(end_ts),
                            "deadline": str(DEADLINE_EVENING),
                        })

                if duration_ms:
                    durations.append(duration_ms)

            if durations:
                job_stats["avg_duration_ms"] = round(sum(durations) / len(durations))

            result["evening"]["stats"][job] = job_stats

        # 隔夜全球作业时效
        for job in CRITICAL_JOBS_MORNING:
            rows = _query_pg(
                "SELECT ts AT TIME ZONE 'Asia/Shanghai' AS local_ts, "
                "       status, duration_ms, note "
                "FROM ingest_log "
                "WHERE job = %s AND ts::date BETWEEN %s AND %s "
                "ORDER BY ts DESC",
                (job, start_date, end_date),
            )

            job_stats = {
                "total_runs": len(rows),
                "on_time": 0,
                "late": 0,
                "fail": 0,
                "avg_duration_ms": 0,
            }

            durations = []
            for row in rows:
                local_ts = row[0]
                status = row[1]
                duration_ms = row[2]

                if status in ("FAIL", "MISS"):
                    job_stats["fail"] += 1
                    continue

                if local_ts is not None:
                    end_ts = local_ts
                    if duration_ms:
                        end_ts = local_ts + timedelta(milliseconds=duration_ms)

                    if end_ts.time() <= DEADLINE_MORNING:
                        job_stats["on_time"] += 1
                    else:
                        job_stats["late"] += 1
                        result["morning"]["violations"].append({
                            "date": str(local_ts.date()),
                            "job": job,
                            "end_ts": str(end_ts),
                            "deadline": str(DEADLINE_MORNING),
                        })

                if duration_ms:
                    durations.append(duration_ms)

            if durations:
                job_stats["avg_duration_ms"] = round(sum(durations) / len(durations))

            result["morning"]["stats"][job] = job_stats

        conn.close()

    # 判定
    total_violations = (
        len(result["evening"]["violations"]) +
        len(result["morning"]["violations"])
    )
    if total_violations == 0:
        result["status"] = "PASS"
    else:
        result["status"] = "FAIL"

    return result


def format_report(result: dict) -> str:
    lines = []
    lines.append("=" * 70)
    lines.append("验收③ 时效性检查报告")
    lines.append("=" * 70)
    lines.append(f"检查天数: {result['days']}")
    lines.append(f"通道: {result['channel']}")
    lines.append(f"状态: {result['status']}")
    lines.append("")

    if "error" in result:
        lines.append(f"[BLOCKED] {result['error']}")
        lines.append("")
        return "\n".join(lines)

    # 收盘全量
    ev = result["evening"]
    lines.append(f"--- 收盘全量（截止 {ev['deadline']}）---")
    for job, stats in ev["stats"].items():
        lines.append(f"  {job}:")
        lines.append(f"    总运行: {stats['total_runs']}")
        lines.append(f"    准时: {stats['on_time']} / 超时: {stats['late']} / 失败: {stats['fail']}")
        lines.append(f"    平均耗时: {stats['avg_duration_ms']} ms")
        pass_rate = (
            stats['on_time'] / max(1, stats['total_runs'] - stats['fail'])
            if (stats['total_runs'] - stats['fail']) > 0 else 0
        )
        lines.append(f"    准时率: {pass_rate:.1%}")
    if ev["violations"]:
        lines.append(f"  超时违规 ({len(ev['violations'])} 次):")
        for v in ev["violations"][:10]:
            lines.append(f"    {v['date']} {v['job']}: 结束 {v['end_ts']} > 截止 {v['deadline']}")
    lines.append("")

    # 隔夜全球
    mo = result["morning"]
    lines.append(f"--- 隔夜全球（截止 {mo['deadline']}）---")
    for job, stats in mo["stats"].items():
        lines.append(f"  {job}:")
        lines.append(f"    总运行: {stats['total_runs']}")
        lines.append(f"    准时: {stats['on_time']} / 超时: {stats['late']} / 失败: {stats['fail']}")
        lines.append(f"    平均耗时: {stats['avg_duration_ms']} ms")
        pass_rate = (
            stats['on_time'] / max(1, stats['total_runs'] - stats['fail'])
            if (stats['total_runs'] - stats['fail']) > 0 else 0
        )
        lines.append(f"    准时率: {pass_rate:.1%}")
    if mo["violations"]:
        lines.append(f"  超时违规 ({len(mo['violations'])} 次):")
        for v in mo["violations"][:10]:
            lines.append(f"    {v['date']} {v['job']}: 结束 {v['end_ts']} > 截止 {v['deadline']}")
    lines.append("")

    lines.append("=" * 70)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="验收③ 时效性检查：ingest_log 截止时间校验",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--days", type=int, default=20,
                        help="检查最近 N 天（默认 20）")
    parser.add_argument(
        "--channel", choices=["pg", "api"], default="pg",
        help="数据通道",
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    result = run_timeliness_check(args.days, args.channel)

    if args.json:
        def _ser(obj):
            if isinstance(obj, (date, datetime)):
                return str(obj)
            raise TypeError
        print(json.dumps(result, indent=2, default=_ser))
    else:
        print(format_report(result))

    sys.exit(0 if result["status"] in ("PASS", "BLOCKED") else 1)


if __name__ == "__main__":
    main()
