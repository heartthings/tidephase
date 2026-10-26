#!/usr/bin/env python3
"""
验证「上影线试盘」是否比「缩量堆积→放量试盘(2.18%)」更能促成 T+1 涨停

上影线 = high - max(open, close)，代表当日冲高回落(主力拉升试探后回撤)。
对比信号：
  S5  缩量堆积 → 放量试盘(基线, 涨3-7%)          已测得 2.18%
  S6a 缩量堆积 + 放量 + 上影线>2%收盘 + 涨0-7%
  S6b 缩量堆积 + 放量 + 上影线>2倍实体 + 涨-2~7%(允许微跌)
  S6c 仅放量 + 上影线>2%收盘(无缩量堆积前提) + 涨0-7%
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
        open_ = g["open"].values.astype(float)
        high = g["high"].values.astype(float)
        close = g["close"].values.astype(float)
        vol = g["volume"].values.astype(float)
        pct = g["pct"].values.astype(float)
        date = g["date"].values
        n = len(g)

        vol20 = pd.Series(vol).rolling(20).mean().values

        for i in range(n - 1):
            if np.isnan(pct[i]) or np.isnan(pct[i + 1]):
                continue
            label = 1 if pct[i + 1] >= thr else 0

            # 上影线长度(相对收盘)
            upper_body = max(open_[i], close[i])
            upper = high[i] - upper_body          # 上影线绝对值
            upper_ratio = upper / close[i] if close[i] > 0 else 0.0   # 上影线/收盘
            body = abs(close[i] - open_[i])        # 实体
            body_ratio = body / close[i] if close[i] > 0 else 0.0

            s5 = s6a = s6b = s6c = 0
            if i >= 41 and not np.isnan(vol20[i]) and vol20[i] > 0:
                # 缩量堆积前置: 近20日均量 < 更早20日均量*0.8 且 20日振幅<15%
                win_close = close[i - 20:i]
                if win_close.min() > 0:
                    amp = (win_close.max() - win_close.min()) / win_close.min()
                else:
                    amp = 99.0
                vol_win = np.nanmean(vol[i - 20:i])
                vol_prev = np.nanmean(vol[i - 40:i - 20])
                accumulated = (vol_prev > 0 and vol_win < vol_prev * 0.8) and (amp < 0.15)

                # 放量: 当日量 > 2倍20日均量
                fang = vol[i] > vol20[i] * 2

                # S5 基线(缩量堆积 + 放量 + 涨3-7%)
                if accumulated and fang and (3.0 <= pct[i] < 7.0):
                    s5 = 1

                # S6a 缩量堆积 + 放量 + 上影线>2% + 涨0-7%
                if accumulated and fang and upper_ratio > 0.02 and (0.0 <= pct[i] < 7.0):
                    s6a = 1

                # S6b 缩量堆积 + 放量 + 上影线>2倍实体(且>0.5%) + 涨-2~7%
                if (accumulated and fang and upper_ratio > 0.005
                        and upper_ratio > 2.0 * body_ratio and (-2.0 <= pct[i] < 7.0)):
                    s6b = 1

                # S6c 仅放量 + 上影线>2%(无缩量堆积前提) + 涨0-7%
                if fang and upper_ratio > 0.02 and (0.0 <= pct[i] < 7.0):
                    s6c = 1

            rows.append((date[i], code, pct[i], label, s5, s6a, s6b, s6c))

    return pd.DataFrame(rows, columns=["date", "code", "pct", "label", "s5", "s6a", "s6b", "s6c"])


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
        "S5_缩量堆积→放量试盘": "s5",
        "S6a_缩量堆积+放量+上影线>2%": "s6a",
        "S6b_缩量堆积+放量+上影线>2倍实体": "s6b",
        "S6c_仅放量+上影线>2%(无堆积)": "s6c",
    }
    print(f"\n=== <300亿 口径 ===")
    print(f"{'信号':<30} {'样本':>7} {'T+1涨停':>8} {'命中率':>8} {'vs基准':>8}")
    for name, col in signals.items():
        sub = feat[(feat[col] == 1) & u300]
        if len(sub) == 0:
            continue
        mult = sub["label"].mean() / (base_u300 / 100.0)
        print(f"{name:<30} {len(sub):>7} {int(sub['label'].sum()):>8} "
              f"{sub['label'].mean()*100:>7.2f}% {mult:>7.2f}x")


if __name__ == "__main__":
    main()