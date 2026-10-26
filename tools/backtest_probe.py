#!/usr/bin/env python3
"""
验证复合信号「缩量堆积 → 放量试盘」是否促成 T+1 涨停

用户假设: 前期缩量堆积(小阴小阳,量能萎缩) + 后期放量试盘 -> 容易涨停
之前结论: S1 纯缩量堆积 0.48%(无效), S4 低位放量启动 4.60%(最强)
本脚本: 新增 S5 复合时序信号 = 缩量堆积(量能萎缩+窄幅) + 当日放量试盘(2倍量+涨3-7%)

关键: 之前 S1(缩量) 与 S4(放量启动) 是"分开测的独立信号"；
     用户的直觉是"先缩量堆积 → 后放量试盘"的复合时序, 从未测过, 本脚本补测。
"""
import sys
from pathlib import Path

import psycopg2
import pandas as pd
import numpy as np
import yaml

SECRETS_PATH = Path("/home/hello/application/dev/market-datalayer/configs/secrets.yaml")


def get_conn():
    with open(SECRETS_PATH) as f:
        s = yaml.safe_load(f) or {}
    db = s.get("database", {})
    return psycopg2.connect(
        host="127.0.0.1", port=15432, dbname="market_tsdb",
        user="duser_reader", password=db.get("duser_reader_password", ""),
    )


def limit_threshold(code: str) -> float:
    return 19.8 if code.startswith(("sz30", "sh68")) else 9.8


def load_data(conn) -> pd.DataFrame:
    sql = """
        SELECT date, code, open, high, low, close, pct, volume, circ_mv
        FROM stock_daily
        WHERE (code LIKE 'sh%' OR code LIKE 'sz%') AND close > 0
        ORDER BY code, date
    """
    return pd.read_sql(sql, conn)


def compute(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for code, g in df.groupby("code"):
        g = g.sort_values("date").reset_index(drop=True)
        thr = limit_threshold(code)
        close = g["close"].values.astype(float)
        vol = g["volume"].values.astype(float)
        pct = g["pct"].values.astype(float)
        date = g["date"].values
        n = len(g)

        vol5 = pd.Series(vol).rolling(5).mean().values
        vol10 = pd.Series(vol).rolling(10).mean().values
        vol20 = pd.Series(vol).rolling(20).mean().values
        vol30 = pd.Series(vol).rolling(30).mean().values
        vol60 = pd.Series(vol).rolling(60).mean().values
        cum3 = pd.Series(pct).rolling(3).sum().values
        cum10 = pd.Series(pct).rolling(10).sum().values
        cum60 = pd.Series(pct).rolling(60).sum().values

        for i in range(n - 1):
            if np.isnan(pct[i]) or np.isnan(pct[i + 1]):
                continue
            label = 1 if pct[i + 1] >= thr else 0

            # S1 缩量堆积(原版, 纯缩量横盘)
            s1 = 0
            if i >= 10 and not np.isnan(vol10[i]) and not np.isnan(vol30[i]):
                recent = pct[i - 9:i + 1]
                if (np.nanmax(np.abs(recent)) < 3.5 and abs(cum10[i]) < 5
                        and vol10[i] < vol30[i] * 0.7):
                    s1 = 1

            # S4 低位放量启动(原版)
            s4 = 0
            if i >= 60 and not np.isnan(vol60[i]) and not np.isnan(cum60[i]):
                if cum60[i] < -20 and vol[i] > vol60[i] * 2 and pct[i] > 5:
                    s4 = 1

            # S5 缩量堆积 -> 放量试盘(复合)
            s5 = 0
            if i >= 41 and not np.isnan(vol20[i]) and vol20[i] > 0:
                win_close = close[i - 20:i]          # 近期20日
                prev_close = close[i - 40:i - 20]    # 更早20日
                if win_close.min() > 0:
                    amp = (win_close.max() - win_close.min()) / win_close.min()
                else:
                    amp = 99.0
                vol_win = np.nanmean(vol[i - 20:i])
                vol_prev = np.nanmean(vol[i - 40:i - 20])
                # 缩量堆积: 近20日均量萎缩(比更早20日 < 0.8) 且 窄幅(振幅<15%)
                accumulated = (vol_prev > 0 and vol_win < vol_prev * 0.8) and (amp < 0.15)
                # 放量试盘: 当日量>2倍20日均量 且 涨3~7%(未涨停未暴涨)
                probe = (vol[i] > vol20[i] * 2) and (3.0 <= pct[i] < 7.0)
                if accumulated and probe:
                    s5 = 1

            # S5b 放宽: 试盘涨幅 3% ~ 涨停前(涨停前任意放量)
            s5b = 0
            if i >= 41 and not np.isnan(vol20[i]) and vol20[i] > 0:
                win_close = close[i - 20:i]
                if win_close.min() > 0:
                    amp = (win_close.max() - win_close.min()) / win_close.min()
                else:
                    amp = 99.0
                vol_win = np.nanmean(vol[i - 20:i])
                vol_prev = np.nanmean(vol[i - 40:i - 20])
                accumulated = (vol_prev > 0 and vol_win < vol_prev * 0.8) and (amp < 0.15)
                probe = (vol[i] > vol20[i] * 2) and (3.0 <= pct[i] < thr)
                if accumulated and probe:
                    s5b = 1

            rows.append((date[i], code, pct[i], label, s1, s4, s5, s5b))

    return pd.DataFrame(rows, columns=["date", "code", "pct", "label", "s1", "s4", "s5", "s5b"])


def main():
    conn = get_conn()
    df = load_data(conn)
    conn.close()
    print(f"加载 {len(df)} 行日K")

    latest_mv = df.dropna(subset=["circ_mv"]).sort_values("date").groupby("code")["circ_mv"].last()
    feat = compute(df)
    feat["mv"] = feat["code"].map(latest_mv)
    feat["mv_bucket"] = pd.cut(feat["mv"], bins=[0, 50, 100, 300, np.inf],
                               labels=["<50亿", "50-100亿", "100-300亿", ">=300亿"])
    u300 = feat["mv_bucket"].isin(["<50亿", "50-100亿", "100-300亿"])

    base_all = feat["label"].mean() * 100
    base_u300 = feat[u300]["label"].mean() * 100
    print(f"全市场基准命中率: {base_all:.2f}%")
    print(f"<300亿 基准命中率: {base_u300:.2f}%")

    signals = {
        "S1_缩量堆积(原)": "s1",
        "S4_低位放量(原)": "s4",
        "S5_缩量堆积→放量试盘": "s5",
        "S5b_试盘放宽至涨停前": "s5b",
    }
    print(f"\n{'信号':<22} {'样本':>7} {'T+1涨停':>8} {'命中率':>8} {'vs基准':>8}")
    for name, col in signals.items():
        sub = feat[feat[col] == 1]
        if len(sub) == 0:
            print(f"{name:<22} {'0':>7}")
            continue
        print(f"{name:<22} {len(sub):>7} {int(sub['label'].sum()):>8} "
              f"{sub['label'].mean()*100:>7.2f}% {sub['label'].mean()/base_all:>7.2f}x")

    # <300亿 口径
    print(f"\n=== <300亿 口径 ===")
    print(f"{'信号':<22} {'样本':>7} {'T+1涨停':>8} {'命中率':>8} {'vs基准':>8}")
    for name, col in signals.items():
        sub = feat[(feat[col] == 1) & u300]
        if len(sub) == 0:
            continue
        print(f"{name:<22} {len(sub):>7} {int(sub['label'].sum()):>8} "
              f"{sub['label'].mean()*100:>7.2f}% {sub['label'].mean()/base_u300:>7.2f}x")


if __name__ == "__main__":
    main()