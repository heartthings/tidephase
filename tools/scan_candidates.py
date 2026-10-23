#!/usr/bin/env python3
"""
补测信号 + 扫描当前市场候选股

1) 回测 S1b 缩量堆积后放量启动 (T日: 近10日小阴小阳缩量堆积 且 T日放量+上涨)
2) 扫描最新交易日, 用回测有效信号筛候选股:
   - S2 急跌
   - S4 低位放量启动
   - S1b 缩量突破
输出候选股 + 流通市值 + 近5日涨跌幅, 供后续叠加题材
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
    return psycopg2.connect(host="127.0.0.1", port=15432, dbname="market_tsdb",
                            user="duser_reader", password=db.get("duser_reader_password", ""))


def thr(code):
    return 19.8 if code.startswith(("sz30", "sh68")) else 9.8


def load(conn):
    sql = "SELECT date, code, name, open, high, low, close, pct, volume, circ_mv FROM stock_daily WHERE close > 0 ORDER BY code, date"
    return pd.read_sql(sql, conn)


def compute(df):
    rows = []
    for code, g in df.groupby("code"):
        g = g.sort_values("date").reset_index(drop=True)
        th = thr(code)
        pct = g["pct"].values
        vol = g["volume"].values
        hi = g["high"].values
        lo = g["low"].values
        cl = g["close"].values
        n = len(g)
        vol10 = pd.Series(vol).rolling(10).mean().values
        vol30 = pd.Series(vol).rolling(30).mean().values
        vol60 = pd.Series(vol).rolling(60).mean().values
        cum3 = pd.Series(pct).rolling(3).sum().values
        cum10 = pd.Series(pct).rolling(10).sum().values
        cum60 = pd.Series(pct).rolling(60).sum().values
        for i in range(n - 1):
            if np.isnan(pct[i]) or np.isnan(pct[i + 1]):
                continue
            label = 1 if pct[i + 1] >= th else 0
            s1b = 0
            if i >= 10 and not np.isnan(vol10[i]) and not np.isnan(vol30[i]):
                recent = pct[i - 9:i + 1]
                if (np.nanmax(np.abs(recent)) < 3.5 and abs(cum10[i]) < 5
                        and vol10[i] < vol30[i] * 0.7
                        and vol[i] > vol10[i] * 1.5 and pct[i] > 3):
                    s1b = 1
            s2 = 1 if (i >= 3 and (cum3[i] < -10 or pct[i] < -6)) else 0
            s4 = 0
            if i >= 60 and not np.isnan(vol60[i]) and not np.isnan(cum60[i]):
                if cum60[i] < -20 and vol[i] > vol60[i] * 2 and pct[i] > 5:
                    s4 = 1
            rows.append((g["date"].iloc[i], code, g["name"].iloc[i], pct[i], label, s1b, s2, s4,
                         g["circ_mv"].iloc[i]))
    return pd.DataFrame(rows, columns=["date", "code", "name", "pct", "label", "s1b", "s2", "s4", "circ_mv"])


def main():
    conn = get_conn()
    df = load(conn)
    conn.close()
    print(f"加载 {len(df)} 行")
    f = compute(df)
    latest_mv = df.dropna(subset=["circ_mv"]).sort_values("date").groupby("code")["circ_mv"].last()
    f["mv"] = f["code"].map(latest_mv)

    # 回测 S1b
    sub = f[f["s1b"] == 1]
    s300 = sub[sub["mv"] < 300]
    print(f"\n[S1b 缩量突破] <300亿 样本 {len(s300)} 命中 {s300['label'].sum()} 命中率 {s300['label'].mean()*100:.2f}% (基准1.34%)")
    for b in [(0, 50), (50, 100), (100, 300)]:
        bb = s300[(s300["mv"] >= b[0]) & (s300["mv"] < b[1])]
        if len(bb):
            print(f"  {b[0]}-{b[1]}亿: n={len(bb)} 命中率 {bb['label'].mean()*100:.2f}%")

    # 扫描最新交易日
    last_date = f["date"].max()
    print(f"\n=== 最新交易日 {last_date} 触发信号的候选股 ===")
    cur = f[f["date"] == last_date].copy()
    for sig, name in [("s2", "急跌"), ("s4", "低位放量"), ("s1b", "缩量突破")]:
        c = cur[cur[sig] == 1]
        c300 = c[c["mv"] < 300]
        print(f"\n[{name}] 触发 {len(c300)} 只 (<300亿):")
        print(c300[["code", "name", "mv", "pct"]].sort_values("mv").to_string(index=False))


if __name__ == "__main__":
    main()