#!/usr/bin/env python3
"""
验证「低位 + 上影线试盘」组合，并补测「低位放量 + 光头阳线(无上影)」

对比信号(<300亿, T+1涨停):
  S4  低位放量启动: cum60<-20 & vol>2*vol60 & pct>5
  S6c 放量上影线(无堆积): vol>2*vol20 & 上影线>2% & 0<=pct<7
  S7  低位+上影线试盘(涨0-7): cum60<-20 & vol>2*vol20 & 上影线>2% & 0<=pct<7
  S8  低位+上影线试盘(涨3-7): cum60<-20 & vol>2*vol20 & 上影线>2% & 3<=pct<7
  S9  S4基础上加上影线: cum60<-20 & vol>2*vol60 & 上影线>2% & pct>5
  S10 低位放量+光头阳线: cum60<-20 & vol>2*vol60 & pct>5 & 上影线<1%
"""
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
        open_ = g["open"].values.astype(float)
        high = g["high"].values.astype(float)
        close = g["close"].values.astype(float)
        vol = g["volume"].values.astype(float)
        pct = g["pct"].values.astype(float)
        date = g["date"].values
        n = len(g)

        vol20 = pd.Series(vol).rolling(20).mean().values
        vol60 = pd.Series(vol).rolling(60).mean().values
        cum60 = pd.Series(pct).rolling(60).sum().values

        for i in range(n - 1):
            if np.isnan(pct[i]) or np.isnan(pct[i + 1]):
                continue
            label = 1 if pct[i + 1] >= thr else 0

            upper = high[i] - max(open_[i], close[i])
            upper_ratio = upper / close[i] if close[i] > 0 else 0.0

            s4 = s6c = s7 = s8 = s9 = s10 = 0

            # S4 低位放量启动
            if i >= 60 and not np.isnan(vol60[i]) and not np.isnan(cum60[i]):
                if cum60[i] < -20 and vol[i] > vol60[i] * 2 and pct[i] > 5:
                    s4 = 1
                    # S10 低位放量 + 光头阳线(上影<1%)
                    if upper_ratio < 0.01:
                        s10 = 1

            # S6c 放量上影线(无堆积)
            if i >= 41 and not np.isnan(vol20[i]) and vol20[i] > 0:
                if vol[i] > vol20[i] * 2 and upper_ratio > 0.02 and (0.0 <= pct[i] < 7.0):
                    s6c = 1

            # S7/S8/S9 低位组合
            if i >= 60 and not np.isnan(cum60[i]) and cum60[i] < -20 \
                    and not np.isnan(vol20[i]) and vol20[i] > 0:
                fang20 = vol[i] > vol20[i] * 2
                fang60 = not np.isnan(vol60[i]) and vol[i] > vol60[i] * 2
                if fang20 and upper_ratio > 0.02 and (0.0 <= pct[i] < 7.0):
                    s7 = 1
                if fang20 and upper_ratio > 0.02 and (3.0 <= pct[i] < 7.0):
                    s8 = 1
                if fang60 and upper_ratio > 0.02 and pct[i] > 5:
                    s9 = 1

            rows.append((date[i], code, pct[i], label, s4, s6c, s7, s8, s9, s10))

    return pd.DataFrame(rows, columns=["date", "code", "pct", "label", "s4", "s6c", "s7", "s8", "s9", "s10"])


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
    print(f"全市场基准: {base_all:.2f}% | <300亿 基准: {base_u300:.2f}%")

    signals = {
        "S4_低位放量启动": "s4",
        "S6c_放量上影线(无堆积)": "s6c",
        "S7_低位+上影线试盘(涨0-7)": "s7",
        "S8_低位+上影线试盘(涨3-7)": "s8",
        "S9_S4基础上加上影线": "s9",
        "S10_低位放量+光头阳线": "s10",
    }
    print(f"\n=== <300亿 口径 ===")
    print(f"{'信号':<26} {'样本':>7} {'T+1涨停':>8} {'命中率':>8} {'vs基准':>7}")
    for name, col in signals.items():
        sub = feat[(feat[col] == 1) & u300]
        if len(sub) == 0:
            print(f"{name:<26} {'0':>7}")
            continue
        mult = sub["label"].mean() / (base_u300 / 100.0)
        print(f"{name:<26} {len(sub):>7} {int(sub['label'].sum()):>8} "
              f"{sub['label'].mean()*100:>7.2f}% {mult:>6.2f}x")


if __name__ == "__main__":
    main()