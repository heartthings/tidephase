#!/usr/bin/env python3
"""
涨停形态回测 (T+1 当日涨停为预测目标)

数据: stock_daily (回填后含约1年日K, pct 为自算准确涨跌幅)
涨停判定: 按代码前缀
  - sz30 / sh68 -> 20% (阈值 19.8)
  - 其余主板    -> 10% (阈值 9.8)
流通市值: 用 stock_daily 最新 circ_mv 做静态分档 (<50 / 50-100 / 100-300 / >=300亿)

信号 (T 日收盘后计算, 预测 T+1 涨停):
  S1 缩量堆积调整: 近10日 |pct| 均 < 3.5% 且 10日累计|涨跌| < 5% 且 近10日均量 < 近30日均量 * 0.7
  S2 急跌:        近3日累计 pct < -10% 或 单日 pct < -6%
  S3 平台突破:    近20日振幅 < 12% 且 T日 pct > 3% 且 T日量 > 近20日均量 * 1.8
  S4 低位放量启动: 近60日累计 < -20% 且 T日量 > 近60日均量 * 2 且 T日 pct > 5%

输出: 每个信号 (按市值分档) 样本数 / T+1涨停数 / 命中率, 对比全市场基准
"""
import sys
from pathlib import Path

import psycopg2
import pandas as pd
import numpy as np
import yaml

SECRETS_PATH = Path(__file__).resolve().parent.parent / "configs" / "secrets.yaml"


def get_conn():
    with open(SECRETS_PATH) as f:
        secrets = yaml.safe_load(f) or {}
    db = secrets.get("database", {})
    return psycopg2.connect(
        host="127.0.0.1", port=15432, dbname="market_tsdb",
        user="duser_reader", password=db.get("duser_reader_password", ""),
    )


def limit_threshold(code: str) -> float:
    """返回涨停 pct 阈值."""
    if code.startswith(("sz30", "sh68")):
        return 19.8
    return 9.8


def load_data(conn) -> pd.DataFrame:
    sql = """
        SELECT date, code, open, high, low, close, pct, volume, circ_mv
        FROM stock_daily
        WHERE (code LIKE 'sh%' OR code LIKE 'sz%')
          AND close > 0
        ORDER BY code, date
    """
    return pd.read_sql(sql, conn)


def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """按 code 分组计算滚动特征. 返回带信号与 label 的 dataframe."""
    rows = []
    for code, g in df.groupby("code"):
        g = g.sort_values("date").reset_index(drop=True)
        thr = limit_threshold(code)
        close = g["close"].values
        vol = g["volume"].values
        pct = g["pct"].values
        date = g["date"].values
        n = len(g)

        # 滚动均值
        vol10 = pd.Series(vol).rolling(10).mean().values
        vol20 = pd.Series(vol).rolling(20).mean().values
        vol30 = pd.Series(vol).rolling(30).mean().values
        vol60 = pd.Series(vol).rolling(60).mean().values
        cum3 = pd.Series(pct).rolling(3).sum().values
        cum10 = pd.Series(pct).rolling(10).sum().values
        cum60 = pd.Series(pct).rolling(60).sum().values
        # 20日振幅
        hi20 = pd.Series(g["high"].values).rolling(20).max().values
        lo20 = pd.Series(g["low"].values).rolling(20).min().values

        for i in range(n - 1):  # 需要 i+1 的 label
            if np.isnan(pct[i]) or np.isnan(pct[i + 1]):
                continue
            # label: T+1 是否涨停
            label = 1 if pct[i + 1] >= thr else 0

            # S1 缩量堆积
            s1 = 0
            if i >= 10 and not np.isnan(vol10[i]) and not np.isnan(vol30[i]):
                recent = pct[i - 9:i + 1]
                if (np.nanmax(np.abs(recent)) < 3.5 and abs(cum10[i]) < 5
                        and vol10[i] < vol30[i] * 0.7):
                    s1 = 1
            # S2 急跌
            s2 = 1 if (i >= 3 and (cum3[i] < -10 or pct[i] < -6)) else 0
            # S3 平台突破
            s3 = 0
            if i >= 20 and hi20 is not None and not np.isnan(vol20[i]):
                amp = (hi20[i] - lo20[i]) / lo20[i] if lo20[i] > 0 else 99
                if amp < 0.12 and pct[i] > 3 and vol[i] > vol20[i] * 1.8:
                    s3 = 1
            # S4 低位放量启动
            s4 = 0
            if i >= 60 and not np.isnan(vol60[i]) and not np.isnan(cum60[i]):
                if cum60[i] < -20 and vol[i] > vol60[i] * 2 and pct[i] > 5:
                    s4 = 1

            rows.append((date[i], code, pct[i], label, s1, s2, s3, s4))

    return pd.DataFrame(rows, columns=["date", "code", "pct", "label", "s1", "s2", "s3", "s4"])


def main():
    conn = get_conn()
    df = load_data(conn)
    conn.close()
    print(f"加载 {len(df)} 行 日K")

    # 静态 circ_mv 分档 (最新值)
    latest_mv = df.dropna(subset=["circ_mv"]).sort_values("date").groupby("code")["circ_mv"].last()
    feat = compute_features(df)
    feat["mv"] = feat["code"].map(latest_mv)
    feat["mv_bucket"] = pd.cut(feat["mv"],
                               bins=[0, 50, 100, 300, np.inf],
                               labels=["<50亿", "50-100亿", "100-300亿", ">=300亿"])  # circ_mv 单位是亿元

    signals = {"s1_缩量堆积": "s1", "s2_急跌": "s2", "s3_平台突破": "s3", "s4_低位放量": "s4"}

    # 全市场基准 (全部样本, 含所有市值)
    base_n = len(feat)
    base_hit = feat["label"].sum()
    print(f"\n全市场基准: 样本 {base_n} | T+1涨停 {base_hit} | 命中率 {base_hit/base_n*100:.2f}%")
    print(f"<300亿基准: {feat[feat['mv_bucket']!='>=300亿']['label'].mean()*100:.2f}%\n")

    print(f"{'信号':<12} {'市值档':<10} {'样本':>6} {'涨停':>6} {'命中率':>8}")
    for name, col in signals.items():
        sub = feat[feat[col] == 1]
        for bucket in ["<50亿", "50-100亿", "100-300亿", ">=300亿"]:
            b = sub[sub["mv_bucket"] == bucket]
            if len(b) == 0:
                continue
            rate = b["label"].mean() * 100
            print(f"{name:<12} {bucket:<10} {len(b):>6} {b['label'].sum():>6} {rate:>7.2f}%")

    # 汇总: 每个信号 <300亿
    print(f"\n{'信号':<12} {'<300亿样本':>10} {'<300亿涨停':>10} {'命中率':>8} {'全市场基准':>10}")
    for name, col in signals.items():
        sub = feat[feat[col] == 1]
        s300 = sub[sub["mv_bucket"].isin(["<50亿", "50-100亿", "100-300亿"])]
        if len(s300) == 0:
            continue
        print(f"{name:<12} {len(s300):>10} {s300['label'].sum():>10} {s300['label'].mean()*100:>7.2f}% {base_hit/base_n*100:>9.2f}%")


if __name__ == "__main__":
    main()