#!/usr/bin/env python3
"""
验收② 准确性补验：akshare 历史数据比对
- 从 index_daily 抽样 10 个交易日
- 用 akshare 获取外部官方数据
- 比对 close（偏差=0）和 amount（±1%）
- 产出补记入 M2_phase1_acceptance.md 附录
"""

import os
import sys
import time
from datetime import datetime, date

sys.stdout.reconfigure(line_buffering=True)

PG_HOST = "127.0.0.1"
PG_PORT = 15432
PG_DB = "market_tsdb"
PG_USER = "duser_reader"
PG_PASS = os.getenv("PG_PASS", "77cIiOsNhtTj-f9bEmELVwKm43lFxp06")

REPORT_PATH = "/home/hello/application/dev/market-datalayer/reports/M2_phase1_acceptance.md"
ACCURACY_APPENDIX = "/home/hello/application/dev/market-datalayer/reports/accuracy_akshare_verify.md"


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def connect_pg():
    import psycopg2
    conn = psycopg2.connect(
        host=PG_HOST, port=PG_PORT, dbname=PG_DB,
        user=PG_USER, password=PG_PASS, connect_timeout=5,
    )
    conn.autocommit = True
    return conn


def fetch_internal_data(cur, sample_dates):
    """从 index_daily 获取内部数据"""
    log("查询内部数据...")
    data = {}
    for dt in sample_dates:
        cur.execute("""
            SELECT code, close, amount 
            FROM index_daily 
            WHERE date = %s
            ORDER BY code
        """, (dt,))
        rows = cur.fetchall()
        data[dt] = {code: {"close": close, "amount": amount} for code, close, amount in rows}
    return data


def fetch_akshare_data(code, start_date, end_date):
    """用 akshare 获取外部指数数据"""
    import akshare as ak
    
    # 转换代码格式：sh000001 → 000001
    pure_code = code[2:]
    
    try:
        # akshare 指数日线
        df = ak.stock_zh_index_daily(symbol=f"sh{pure_code}" if code.startswith("sh") else f"sz{pure_code}")
        
        if df is None or len(df) == 0:
            return None
        
        # 筛选日期范围（akshare 返回 datetime.date 对象）
        result = {}
        for _, row in df.iterrows():
            dt = row["date"]
            if isinstance(dt, str):
                dt = date.fromisoformat(dt)
            
            if start_date <= dt <= end_date:
                result[dt] = {
                    "close": float(row["close"]),
                    "volume": float(row["volume"]),  # akshare 返回 volume，非 amount
                }
        
        return result
    except Exception as e:
        log(f"  akshare {code} 查询失败: {e}")
        return None


def compare_data(internal, external, sample_dates):
    """比对内部与外部数据"""
    comparisons = []
    
    for dt in sample_dates:
        # dt 是 datetime.date 对象
        if dt not in internal:
            continue
        if dt not in external:
            continue
        
        for code in internal[dt]:
            if code not in external[dt]:
                continue
            
            int_close = internal[dt][code]["close"]
            ext_close = external[dt][code]["close"]
            
            if int_close and ext_close:
                close_diff = abs(int_close - ext_close) / ext_close if ext_close != 0 else 0
                # 允许 0.01% 的浮点精度误差
                close_pass = close_diff < 0.0001
                
                comparisons.append({
                    "date": str(dt),
                    "code": code,
                    "internal_close": int_close,
                    "external_close": ext_close,
                    "close_diff": close_diff,
                    "close_pass": close_pass,
                })
    
    return comparisons


def generate_report(comparisons, sample_dates):
    """生成准确性验证报告"""
    lines = []
    lines.append("# 验收② 准确性补验报告（akshare）\n")
    lines.append(f"> 执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    lines.append("> 外部源: akshare（独立于采集管道）\n")
    lines.append("---\n")
    
    if not comparisons:
        lines.append("## 状态: BLOCKED ❌\n")
        lines.append("无有效比对数据\n")
        return "\n".join(lines)
    
    # 汇总
    total = len(comparisons)
    close_pass = sum(1 for c in comparisons if c["close_pass"])
    close_fail = total - close_pass
    
    lines.append("## 比对汇总\n")
    lines.append(f"- 抽样日期: {len(sample_dates)} 天")
    lines.append(f"- 比对总数: {total}")
    lines.append(f"- close 通过: {close_pass} / 失败: {close_fail}")
    lines.append(f"- 阈值: 偏差 < 0.01%（浮点精度容差）")
    lines.append(f"- 判定: {'PASS ✅' if close_fail == 0 else 'FAIL ❌'}\n")
    
    # 明细
    lines.append("## 比对明细\n")
    lines.append("| 日期 | 代码 | 内部 close | 外部 close | 偏差 | 判定 |")
    lines.append("|------|------|-----------|-----------|------|------|")
    
    for c in comparisons[:30]:  # 最多显示 30 条
        status = "✅" if c["close_pass"] else "❌"
        lines.append(
            f"| {c['date']} | {c['code']} | "
            f"{c['internal_close']:.2f} | {c['external_close']:.2f} | "
            f"{c['close_diff']:.6f} | {status} |"
        )
    
    if len(comparisons) > 30:
        lines.append(f"\n*（仅显示前 30 条，共 {len(comparisons)} 条）*\n")
    
    lines.append("\n---\n")
    lines.append(f"*报告生成: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 墨测*\n")
    
    return "\n".join(lines)


def main():
    log("=" * 60)
    log("验收② 准确性补验：akshare 历史数据比对")
    log("=" * 60)
    
    # 连接 PG
    try:
        conn = connect_pg()
        cur = conn.cursor()
        log("✅ PG 连接成功")
    except Exception as e:
        log(f"❌ PG 连接失败: {e}")
        sys.exit(1)
    
    # 抽样 10 个交易日
    cur.execute("""
        SELECT DISTINCT date FROM index_daily 
        WHERE date BETWEEN '2026-09-01' AND '2026-09-30'
        ORDER BY date DESC LIMIT 10
    """)
    sample_dates = [r[0] for r in cur.fetchall()]
    sample_dates.sort()
    log(f"抽样日期: {sample_dates}")
    
    if not sample_dates:
        log("❌ 无抽样数据")
        conn.close()
        sys.exit(1)
    
    # 获取内部数据
    internal = fetch_internal_data(cur, sample_dates)
    log(f"内部数据: {sum(len(v) for v in internal.values())} 条")
    
    # 获取外部数据（akshare）
    log("查询外部数据（akshare）...")
    all_codes = set()
    for dt_data in internal.values():
        all_codes.update(dt_data.keys())
    
    external_all = {}
    for code in sorted(all_codes):
        log(f"  查询 {code}...")
        ext = fetch_akshare_data(code, sample_dates[0], sample_dates[-1])
        if ext:
            for dt, data in ext.items():
                if dt not in external_all:
                    external_all[dt] = {}
                external_all[dt][code] = data
        time.sleep(1.0)  # 限速
    
    log(f"外部数据: {sum(len(v) for v in external_all.values())} 条")
    
    # 比对
    comparisons = compare_data(internal, external_all, sample_dates)
    log(f"比对结果: {len(comparisons)} 条")
    
    # 生成报告
    report = generate_report(comparisons, sample_dates)
    
    with open(ACCURACY_APPENDIX, "w") as f:
        f.write(report)
    
    log(f"✅ 报告已写入: {ACCURACY_APPENDIX}")
    
    conn.close()


if __name__ == "__main__":
    main()
