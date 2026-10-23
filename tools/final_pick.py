#!/usr/bin/env python3
"""
最终选股: 最新交易日信号扫描 + 题材关联 + ST排除
有效信号(回测验证): S2 急跌 / S4 低位放量
扫描最新交易日(10-22), 输出 <300亿 非ST 候选股 + 所属热门题材
"""
from pathlib import Path
import psycopg2, pandas as pd, numpy as np, yaml

SECRETS = Path("/home/hello/application/dev/market-datalayer/configs/secrets.yaml")


def conn():
    with open(SECRETS) as f:
        s = yaml.safe_load(f) or {}
    db = s.get("database", {})
    return psycopg2.connect(host="127.0.0.1", port=15432, dbname="market_tsdb",
                            user="duser_reader", password=db.get("duser_reader_password", ""))


# 当前热门题材 (来自 theme_heat hot_concept 10-22)
HOT = ["人形机器人", "机器人", "减速器", "兵装", "重组", "CPO", "光模块",
       "存储", "PCB", "创新药", "军工", "商业航天", "数据要素", "AI应用", "算力",
       "液冷", "低空", "飞行汽车", "冰雪", "MLCC", "先进封装", "固态电池",
       "汽车零部件", "半导体", "光通信", "传媒", "出版", "电网", "电力", "有色"]


def load_ts(conn):
    sql = ("SELECT date, code, name, high, low, close, pct, volume, circ_mv "
           "FROM stock_daily WHERE close>0 ORDER BY code, date")
    return pd.read_sql(sql, conn)


def load_sectors(conn):
    sql = ("SELECT DISTINCT code, sector_name FROM stock_sector_map "
           "WHERE sector_name IS NOT NULL")
    return pd.read_sql(sql, conn)


def compute_signals(df):
    """对最新交易日计算 S2/S4 信号 (含末行, 无 label)."""
    out = []
    for code, g in df.groupby("code"):
        g = g.sort_values("date").reset_index(drop=True)
        pct = g["pct"].values; vol = g["volume"].values
        n = len(g)
        if n < 60:
            continue
        vol60 = pd.Series(vol).rolling(60).mean().values
        i = n - 1  # 最新交易日
        if np.isnan(pct[i]):
            continue
        cum3 = pct[i - 2:i + 1].sum() if i >= 2 else 0
        cum60 = np.nansum(pct[i - 59:i + 1])
        s2 = 1 if (cum3 < -10 or pct[i] < -6) else 0
        s4 = 1 if (cum60 < -20 and vol[i] > vol60[i] * 2 and pct[i] > 5) else 0
        if s2 or s4:
            out.append((g["date"].iloc[i], code, g["name"].iloc[i], g["circ_mv"].iloc[i],
                        round(pct[i], 2), round(cum3, 2), round(cum60, 2), s2, s4))
    return pd.DataFrame(out, columns=["date", "code", "name", "mv", "pct", "cum3", "cum60", "s2", "s4"])


def main():
    c = conn()
    df = load_ts(c)
    sectors = load_sectors(c)
    c.close()

    sig = compute_signals(df)
    # 排除 ST / 北交所 / >=300亿
    sig = sig[~sig["name"].fillna("").str.contains("ST", na=False)]
    sig = sig[sig["mv"] < 300]
    last = sig["date"].max()
    sig = sig[sig["date"] == last]
    print(f"=== 最新交易日 {last} | <300亿 非ST 有效信号候选 ===")

    sec_map = sectors.groupby("code")["sector_name"].apply(list)
    for sig_name, col in [("急跌S2", "s2"), ("低位放量S4", "s4")]:
        sub = sig[sig[col] == 1].copy()
        sub["题材"] = sub["code"].map(sec_map).map(
            lambda x: "、".join([s for s in (x or []) if any(h in s for h in HOT)])[:80] or "")
        print(f"\n[{sig_name}] {len(sub)} 只")
        print(sub[["code", "name", "mv", "pct", "cum3", "cum60", "题材"]]
              .sort_values("mv").to_string(index=False))


if __name__ == "__main__":
    main()