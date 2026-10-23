#!/usr/bin/env python3
"""
连板晋级率回测：首板 -> 二板(剔除一字板) -> 三板+ 更高板

回答：什么条件下，一只票首板后能走出二板、三板乃至更高板。

核心分层（贴合「题材是舞台、情绪是推力」的方法论）：
  1) 晋级阶梯：首板->二板 / 二板->三板 / 三板->四板 / 四板+   （二板拆分：一字板 vs 可参与的换手板）
  2) 流通市值分层：<50 / 50-100 / 100-300 / >=300 亿
  3) 题材聚集度分层：首板当日所属板块当日涨停家数（1=孤板 / 2 / 3-5聚集 / >=6爆发）
  4) 首板形态：首板一字板 vs 换手板

口径：
  涨停: pct >= thr(code)  (sz30/sh68 -> 19.8, 其余 -> 9.8)
  一字板: open==high==low==close 且涨停 (全天一字封死, 无法参与)
  首板: 当日涨停且前一日不涨停
"""
import warnings
from pathlib import Path

import psycopg2
import pandas as pd
import numpy as np
import yaml

warnings.filterwarnings("ignore")

SECRETS = Path("/home/hello/application/dev/market-datalayer/configs/secrets.yaml")


def get_conn():
    with open(SECRETS) as f:
        s = yaml.safe_load(f) or {}
    db = s.get("database", {})
    return psycopg2.connect(host="127.0.0.1", port=15432, dbname="market_tsdb",
                            user="duser_reader", password=db.get("duser_reader_password", ""))


def thr(code: str) -> float:
    return 19.8 if code.startswith(("sz30", "sh68")) else 9.8


def load():
    c = get_conn()
    df = pd.read_sql(
        "SELECT date, code, name, open, high, low, close, pct, circ_mv "
        "FROM stock_daily WHERE (code LIKE 'sh%' OR code LIKE 'sz%') AND close > 0 "
        "ORDER BY code, date", c)
    sectors = pd.read_sql(
        "SELECT DISTINCT code, sector_name FROM stock_sector_map WHERE sector_name IS NOT NULL", c)
    c.close()
    return df, sectors


def build_market_temp(df):
    """每个交易日的全市场涨停家数(情绪温度代理) + 每票每涨停日所属板块的当日涨停家数."""
    threshold = {c: thr(c) for c in df["code"].unique()}
    df["thr"] = df["code"].map(threshold)
    df["is_lu"] = (df["pct"] >= df["thr"]) & df["pct"].notna()
    day_lu = df[df["is_lu"]].groupby("date").size()  # date -> 全市场涨停家数
    return df, day_lu


def main():
    df, sectors = load()
    df, day_lu = build_market_temp(df)

    threshold = {c: thr(c) for c in df["code"].unique()}
    df["thr"] = df["code"].map(threshold)

    # 一字板标志
    df["is_yz"] = (df["open"] == df["high"]) & (df["high"] == df["low"]) & \
                  (df["low"] == df["close"]) & df["is_lu"]

    # 题材聚集度: 只用"具体题材板块"(成分股<=200)判断，规避人工智能/并购重组等大杂烩
    sector_size = sectors.groupby("sector_name")["code"].nunique()
    small_sectors = set(sector_size[sector_size <= 200].index)
    code2sectors_small = sectors[sectors["sector_name"].isin(small_sectors)] \
        .groupby("code")["sector_name"].unique().to_dict()
    lu = df[df["is_lu"]][["date", "code"]].copy()
    lu["sec"] = lu["code"].map(code2sectors_small)
    lu_x = lu.explode("sec").dropna(subset=["sec"])
    sector_day = lu_x.groupby(["date", "sec"]).size()  # (date, sec) -> count

    # 静态最新流通市值(回填历史数据无 circ_mv，用最新值近似，与上一轮回测口径一致)
    latest_mv = df.dropna(subset=["circ_mv"]).sort_values("date").groupby("code")["circ_mv"].last()

    events = []  # 每个首板事件一条
    for code, g in df.groupby("code"):
        g = g.sort_values("date").reset_index(drop=True)
        n = len(g)
        lu_arr = g["is_lu"].to_numpy()
        yz_arr = g["is_yz"].to_numpy()
        pct = g["pct"].to_numpy()
        name = g["name"].iloc[0]
        dates = g["date"].to_numpy()

        i = 0
        while i < n:
            if not lu_arr[i]:
                i += 1
                continue
            if i > 0 and lu_arr[i - 1]:
                # 连板中的后续板，跳过（由首板统一记录）
                i += 1
                continue
            # i 是首板
            board = 1
            j = i
            while j + 1 < n and lu_arr[j + 1]:
                board += 1
                j += 1
            # 二板(i+1)是否一字板
            board2_yz = (board >= 2) and bool(yz_arr[i + 1]) if i + 1 < n and board >= 2 else None
            # 首板是否一字板
            first_yz = bool(yz_arr[i])
            # 首板当日全市场涨停家数
            d = dates[i]
            mkt = int(day_lu.get(d, 0))
            # 题材聚集度: 该票所属"具体题材板块"当日涨停家数的最大值
            secs = code2sectors_small.get(code, [])
            best_cnt = 0
            for s in secs:
                cnt = int(sector_day.get((d, s), 0))
                if cnt > best_cnt:
                    best_cnt = cnt
            events.append({
                "code": code, "name": str(name), "date": d,
                "mv": float(latest_mv.get(code, np.nan)),
                "board": board, "board2_yz": board2_yz, "first_yz": first_yz,
                "mkt_temp": mkt, "sec_cnt": best_cnt,
            })
            i = j + 1  # 跳过整个连板段，推进游标（避免死循环）

    ev = pd.DataFrame(events)
    ev = ev[~ev["name"].str.contains("ST", na=False)]
    print(f"首板事件总数(非ST): {len(ev)}")

    # ---- 晋级阶梯 ----
    print("\n===== 连板晋级阶梯（全市场 非ST） =====")
    print(f"{'阶段':<16} {'样本':>7} {'晋级数':>7} {'晋级率':>8}")
    for board, nxt in [(1, 2), (2, 3), (3, 4), (4, 5)]:
        sub = ev[ev["board"] >= board]
        up = ev[ev["board"] >= nxt]
        if len(sub):
            print(f"{board}板 -> {nxt}板{'':<7} {len(sub):>7} {len(up):>7} {len(up)/len(sub)*100:>7.2f}%")

    # ---- 二板拆一字板 ----
    print("\n===== 二板构成（首板次日） =====")
    n1 = len(ev[ev["board"] >= 1])
    n2 = len(ev[ev["board"] >= 2])
    n2_yz = ev[ev["board2_yz"] == True].shape[0]
    n2_hs = n2 - n2_yz
    print(f"首板 {n1} -> 二板 {n2} (晋级率 {n2/n1*100:.2f}%)")
    print(f"  其中 二板一字板(不可参与) {n2_yz} 只 | 换手二板(可参与) {n2_hs} 只 ({n2_hs/n1*100:.2f}%)")

    # ---- 市值分层 ----
    print("\n===== 二板晋级率 by 流通市值（剔除二板一字板后口径） =====")
    ev["mv_bucket"] = pd.cut(ev["mv"], bins=[0, 50, 100, 300, np.inf],
                            labels=["<50亿", "50-100亿", "100-300亿", ">=300亿"])
    print(f"{'市值档':<12} {'首板':>6} {'二板':>6} {'可参与二板':>8} {'晋级率':>8} {'->三板':>8}")
    for b in ["<50亿", "50-100亿", "100-300亿", ">=300亿"]:
        sub = ev[ev["mv_bucket"] == b]
        if not len(sub):
            continue
        n = len(sub)
        n2 = (sub["board"] >= 2).sum()
        n2_hs = ((sub["board"] >= 2) & (sub["board2_yz"] != True)).sum()
        n3 = (sub["board"] >= 3).sum()
        print(f"{b:<12} {n:>6} {n2:>6} {n2_hs:>8} {n2/n*100:>7.2f}% {n3/n2*100:>7.2f}%")

    # ---- 题材聚集度分层 ----
    print("\n===== 二板晋级率 by 首板当日题材聚集度（所属板块当日涨停家数） =====")
    ev["sec_bucket"] = pd.cut(ev["sec_cnt"], bins=[0, 1, 2, 5, np.inf],
                             labels=["孤板(1)", "2只", "3-5只聚集", ">=6爆发"], include_lowest=True)
    print(f"{'聚集度':<12} {'首板':>6} {'二板':>6} {'可参与二板':>8} {'晋级率':>8} {'->三板':>8}")
    for b in ["孤板(1)", "2只", "3-5只聚集", ">=6爆发"]:
        sub = ev[ev["sec_bucket"] == b]
        if not len(sub):
            continue
        n = len(sub)
        n2 = (sub["board"] >= 2).sum()
        n2_hs = ((sub["board"] >= 2) & (sub["board2_yz"] != True)).sum()
        n3 = (sub["board"] >= 3).sum()
        r3 = n3 / n2 * 100 if n2 else 0
        print(f"{b:<12} {n:>6} {n2:>6} {n2_hs:>8} {n2/n*100:>7.2f}% {r3:>7.2f}%")

    # ---- 首板形态 ----
    print("\n===== 二板晋级率 by 首板形态 =====")
    for label, mask in [("首板换手板", ev["first_yz"] == False), ("首板一字板", ev["first_yz"] == True)]:
        sub = ev[mask]
        if not len(sub):
            continue
        n = len(sub)
        n2 = (sub["board"] >= 2).sum()
        n2_hs = ((sub["board"] >= 2) & (sub["board2_yz"] != True)).sum()
        print(f"{label:<12} 首板{n:>5} 二板{n2:>5} 可参与二板{n2_hs:>5} 晋级率{n2/n*100:>6.2f}%")

    # ---- 情绪温度分层 ----
    print("\n===== 二板晋级率 by 首板当日全市场涨停家数(情绪温度) =====")
    ev["mkt_bucket"] = pd.cut(ev["mkt_temp"], bins=[0, 30, 60, 200],
                             labels=["<30冰点", "30-60正常", ">60高潮"], include_lowest=True)
    for b in ["<30冰点", "30-60正常", ">60高潮"]:
        sub = ev[ev["mkt_bucket"] == b]
        if not len(sub):
            continue
        n = len(sub)
        n2 = (sub["board"] >= 2).sum()
        n2_hs = ((sub["board"] >= 2) & (sub["board2_yz"] != True)).sum()
        print(f"{b:<12} 首板{n:>6} 二板{n2:>6} 可参与二板{n2_hs:>5} 晋级率{n2/n*100:>6.2f}%")


if __name__ == "__main__":
    main()