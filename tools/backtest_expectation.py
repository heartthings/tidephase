#!/usr/bin/env python3
"""
资金「预期你的预期」回测

验证两类场景（以及用户说法之外的边界条件）：
  A. 放量上涨 → 次日一致看多 → 冲高后被资金兑现（追高者被套、不舍得割）
  B. 连续下跌/放量恐慌 → 抛售之后资金反手买（恐慌末端是买点）

数据口径：
  - stock_daily 2025-06-05 ~ 2026-10-23，pct 为百分比
  - 涨停阈值：sz30/sh68→19.8；ST→4.8；其余→9.8
  - 主样本：流通市值 < 300 亿（用户硬约束）；同时给全市场基准
  - T+1/T+2 必须是相邻交易日（用指数日历对齐，跨停牌不计）

用法：
  python tools/backtest_expectation.py daily
  python tools/backtest_expectation.py intraday
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2
import yaml

SECRETS_PATH = Path("/home/hello/application/dev/market-datalayer/configs/secrets.yaml")


def get_conn(user="duser_reader"):
    with open(SECRETS_PATH) as f:
        secrets = yaml.safe_load(f) or {}
    db = secrets.get("database", {})
    return psycopg2.connect(
        host="127.0.0.1", port=15432, dbname="market_tsdb",
        user=user, password=db.get(f"{user}_password", ""),
    )


def limit_threshold(code: str, is_st) -> float:
    if is_st is True or is_st == 1:
        return 4.8
    if code.startswith(("sz30", "sh68")):
        return 19.8
    return 9.8


def query_df(conn, sql: str) -> pd.DataFrame:
    """用 psycopg2 直接取数（本机 pandas 的 read_sql 会误触发 sqlite3）。"""
    cur = conn.cursor()
    cur.execute(sql)
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    cur.close()
    return pd.DataFrame(rows, columns=cols)


def load_daily(conn) -> pd.DataFrame:
    sql = """
        SELECT date, code, open, high, low, close, pct, volume, circ_mv, is_st,
               is_suspended
        FROM stock_daily
        WHERE (code LIKE 'sh%' OR code LIKE 'sz%') AND close > 0
        ORDER BY code, date
    """
    df = query_df(conn, sql)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


def load_index(conn) -> pd.DataFrame:
    sql = """
        SELECT date, pct, close, volume
        FROM index_daily
        WHERE code = 'sh000001'
        ORDER BY date
    """
    df = query_df(conn, sql)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


def build_features(df: pd.DataFrame, index_df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["code", "date"]).reset_index(drop=True)
    df["thr"] = [limit_threshold(c, s) for c, s in zip(df["code"], df["is_st"])]

    g = df.groupby("code", sort=False)
    df["prev_close"] = g["close"].shift(1)
    df["prev_pct"] = g["pct"].shift(1)
    df["vol_ma5"] = g["volume"].transform(
        lambda s: s.shift(1).rolling(5, min_periods=5).mean())
    df["vol_ratio"] = df["volume"] / df["vol_ma5"]
    for w in (3, 5, 10, 20, 60):
        df[f"cum{w}"] = g["pct"].transform(
            lambda s, w=w: s.rolling(w, min_periods=w).sum())
    df["hi60"] = g["high"].transform(lambda s: s.rolling(60, min_periods=60).max())
    df["lo60"] = g["low"].transform(lambda s: s.rolling(60, min_periods=60).min())
    df["close_pos"] = np.where(
        df["high"] > df["low"],
        (df["close"] - df["low"]) / (df["high"] - df["low"]), 1.0)

    # 历史日K 多数不含 circ_mv，用每只票最新流通市值做分档（与既有回测口径一致）
    latest_mv = (df.dropna(subset=["circ_mv"]).sort_values("date")
                 .groupby("code")["circ_mv"].last())
    df["mv_latest"] = df["code"].map(latest_mv)

    # 交易日序号：以指数日历为准，保证 T+1/T+2 为相邻交易日
    cal = {d: i for i, d in enumerate(sorted(index_df["date"].unique()))}
    df["dseq"] = df["date"].map(cal)
    g = df.groupby("code", sort=False)
    df["dseq1"] = g["dseq"].shift(-1)
    df["dseq2"] = g["dseq"].shift(-2)
    df["dseq3"] = g["dseq"].shift(-3)
    df["ok_t1"] = df["dseq1"] == df["dseq"] + 1
    df["ok_t2"] = df["dseq2"] == df["dseq"] + 2
    df["ok_t3"] = df["dseq3"] == df["dseq"] + 3

    for col in ("open", "high", "low", "close", "pct", "volume"):
        df[f"f_{col}"] = g[col].shift(-1)
        df[f"f2_{col}"] = g[col].shift(-2)
        df[f"f3_{col}"] = g[col].shift(-3)

    # 结果变量（单位：%）
    df["t1_ret"] = df["f_pct"]
    df["t1_gap"] = (df["f_open"] / df["close"] - 1) * 100
    df["t1_oc"] = (df["f_close"] / df["f_open"] - 1) * 100
    df["t1_high"] = (df["f_high"] / df["close"] - 1) * 100
    df["t1_close_from_high"] = (df["f_close"] / df["f_high"] - 1) * 100
    bad_fwd = ((df["f_open"] <= 0) | (df["f_close"] <= 0) | (df["f_high"] <= 0))
    for col in ("t1_gap", "t1_oc", "t1_high", "t1_close_from_high"):
        df.loc[bad_fwd, col] = np.nan
    df["t1_fade"] = (df["t1_high"] >= 2) & (df["t1_close_from_high"] <= -2)
    df["t1_trap"] = (df["t1_high"] >= 2) & (df["f_close"] < df["close"])
    df["t1_up"] = df["t1_ret"] > 0
    df["t1_one_word"] = (
        (df["f_open"] == df["f_high"]) & (df["f_high"] == df["f_low"])
        & (df["f_low"] == df["f_close"]) & (df["f_pct"] >= df["thr"]))
    df["t2_ret"] = (df["f2_close"] / df["f_close"] - 1) * 100
    df["t2_from_t"] = (df["f2_close"] / df["close"] - 1) * 100
    df["t2_from_t1open"] = (df["f2_close"] / df["f_open"] - 1) * 100
    df["t3_ret"] = (df["f3_close"] / df["f_close"] - 1) * 100
    df["t3_from_t"] = (df["f3_close"] / df["close"] - 1) * 100
    df.loc[~df["ok_t2"], ["t2_ret", "t2_from_t", "t2_from_t1open"]] = np.nan
    df.loc[~df["ok_t3"], ["t3_ret", "t3_from_t"]] = np.nan

    # 市场宽度（全市场，剔除停牌/无量）
    valid = df[(df["volume"] > 0) & df["pct"].notna()].copy()
    valid["is_lu"] = valid["pct"] >= valid["thr"]
    valid["is_ld"] = valid["pct"] <= -valid["thr"] + 0.2
    valid["is_up"] = valid["pct"] > 0
    valid["is_down"] = valid["pct"] < 0
    breadth = valid.groupby("date").agg(
        limit_up_cnt=("is_lu", "sum"),
        limit_down_cnt=("is_ld", "sum"),
        up_cnt=("is_up", "sum"),
        down_cnt=("is_down", "sum"),
    ).reset_index()
    index_df = index_df.copy()
    index_df["idx_pct"] = index_df["pct"]
    index_df["idx_cum3_prev"] = index_df["idx_pct"].shift(1).rolling(3).sum()
    index_df["idx_cum5_prev"] = index_df["idx_pct"].shift(1).rolling(5).sum()
    index_df["idx_vol_ma5_prev"] = index_df["volume"].shift(1).rolling(5).mean()
    index_df["idx_vol_ratio"] = index_df["volume"] / index_df["idx_vol_ma5_prev"]
    index_df["idx_f_pct"] = index_df["pct"].shift(-1)

    out = df.merge(breadth, on="date", how="left")
    out = out.merge(
        index_df[["date", "idx_pct", "idx_cum3_prev", "idx_cum5_prev",
                  "idx_f_pct", "idx_vol_ratio"]],
        on="date", how="left")
    return out


def pct(x) -> str:
    return f"{x:.2f}%"


def summarize(sub: pd.DataFrame, base: pd.DataFrame, label: str,
              ret_cols=("t1_ret", "t1_oc", "t2_ret")) -> str:
    """输出一行：样本、各收益均值/胜率、冲高回落率、被套率。"""
    n = len(sub)
    if n == 0:
        return f"| {label} | 0 | - | - | - | - | - |"
    t1 = sub["t1_ret"].mean()
    t1w = (sub["t1_ret"] > 0).mean() * 100
    fade = sub["t1_fade"].mean() * 100
    trap = sub["t1_trap"].mean() * 100
    oc = sub["t1_oc"].mean()
    ocw = (sub["t1_oc"] > 0).mean() * 100
    t2 = sub["t2_ret"].mean()
    bt1 = base["t1_ret"].mean()
    bfade = base["t1_fade"].mean() * 100
    return (f"| {label} | {n} | {t1:.2f}% | {t1w:.1f}% | {t1-bt1:+.2f}pp | "
            f"{oc:.2f}% | {ocw:.1f}% | {fade:.1f}% | {trap:.1f}% | "
            f"{t2:.2f}% |")


HEADER = ("| 分组 | 样本 | T+1均涨 | T+1胜率 | 超基准 | T+1开→收 | 开→收胜率 | "
          "冲高回落 | 推动后收跌 | T+2均涨 |")
SEP = "|---|---|---|---|---|---|---|---|---|---|"


def bucket_stats(df: pd.DataFrame, signal_col: str, bucket_col: str,
                 base: pd.DataFrame, title: str, order=None) -> list:
    lines = [f"\n**{title}**\n", HEADER, SEP]
    lines.append(summarize(base, base, "基准(全部)"))
    sub = df[df[signal_col]]
    if order is None:
        order = [x for x in sub[bucket_col].dropna().unique()]
    for b in order:
        s = sub[sub[bucket_col] == b]
        if len(s) < 50:
            continue
        lines.append(summarize(s, base, f"{b}"))
    return lines


def section_a(feat: pd.DataFrame, base: pd.DataFrame):
    print("\n" + "=" * 80)
    print("A. 放量上涨 → 次日一致预期 → 冲高兑现 / 追高被套")
    print("=" * 80)
    print(f"\n样本区间：{feat['date'].min()} ~ {feat['date'].max()}；"
          f"主样本(<300亿, 有T+1)：{len(base)} 行")
    print(f"基准：T+1 均涨 {base['t1_ret'].mean():.3f}% / 胜率 "
          f"{(base['t1_ret']>0).mean()*100:.1f}% / 冲高回落 "
          f"{base['t1_fade'].mean()*100:.1f}% / T+1开→收 "
          f"{base['t1_oc'].mean():.3f}%")

    # A 信号：放量上涨（非涨停）
    a = (feat["pct"] >= 3) & (feat["pct"] < feat["thr"]) & (feat["vol_ratio"] >= 1.5)
    a5 = (feat["pct"] >= 5) & (feat["pct"] < feat["thr"]) & (feat["vol_ratio"] >= 1.5)
    a_fri = a & (pd.to_datetime(feat["date"]).dt.dayofweek == 4)
    a5_fri = a5 & (pd.to_datetime(feat["date"]).dt.dayofweek == 4)
    feat = feat.copy()
    feat["A"] = a
    feat["A5"] = a5
    feat["A_fri"] = a_fri
    feat["A5_fri"] = a5_fri
    feat["dow"] = pd.to_datetime(feat["date"]).dt.dayofweek.map(
        {0: "周一", 1: "周二", 2: "周三", 3: "周四", 4: "周五"})

    feat["pos_bucket"] = pd.cut(
        feat["cum60"], bins=[-np.inf, -30, -15, 0, 15, np.inf],
        labels=["深跌<-30", "-30~-15", "-15~0", "0~15", "强势>15"])
    feat["vol_bucket"] = pd.cut(
        feat["vol_ratio"], bins=[1.5, 2, 3, 5, np.inf],
        labels=["1.5-2x", "2-3x", "3-5x", ">5x"])
    feat["sent_bucket"] = pd.cut(
        feat["limit_up_cnt"], bins=[-np.inf, 30, 60, 100, np.inf],
        labels=["冰点<30", "30-60", "60-100", "火热>100"])
    feat["mv_bucket"] = pd.cut(
        feat["mv_latest"], bins=[0, 50, 100, 300, np.inf],
        labels=["<50亿", "50-100亿", "100-300亿", ">=300亿"])

    print("\n**A0. 基准对照**\n")
    print(HEADER)
    print(SEP)
    print(summarize(base, base, "全部基准"))
    print(summarize(feat[feat["A"]], base, "A: 涨≥3%+量≥1.5x"))
    print(summarize(feat[feat["A5"]], base, "A5: 涨≥5%+量≥1.5x"))
    print(summarize(feat[feat["A_fri"]], base, "A 周五"))
    print(summarize(feat[feat["A5_fri"]], base, "A5 周五"))
    print(summarize(feat[feat["A"] & (~feat["t1_one_word"])],
                    base, "A 剔除次日一字(可追)"))
    # 追高样本：次日高开
    gap_up = feat["A"] & (feat["t1_gap"] >= 0.5)
    print(summarize(feat[gap_up], base, "A 且次日高开≥0.5%"))
    print(summarize(feat[gap_up & (feat["t1_oc"] < 0)], base,
                    "A 高开后收跌(追高亏)"))

    print("\n**A0b. 次日高开≥0.5% 的条件差异（追高是否有效）**\n")
    print(HEADER)
    print(SEP)
    print(summarize(feat[gap_up], base, "A 次日高开≥0.5% 全部"))
    for title, col, order in (
            ("位置", "pos_bucket", ["深跌<-30", "-30~-15", "-15~0", "0~15", "强势>15"]),
            ("情绪", "sent_bucket", ["冰点<30", "30-60", "60-100", "火热>100"]),
            ("星期", "dow", ["周一", "周二", "周三", "周四", "周五"])):
        for b in order:
            s = gap_up & (feat[col] == b)
            if s.sum() >= 50:
                print(summarize(feat[s], base, f"高开·{title}={b}"))
    print(summarize(feat[gap_up & (feat["t1_close_from_high"] >= -0.5)],
                    base, "高开后收在最高(继续强)"))
    print(summarize(feat[gap_up & (feat["t1_close_from_high"] <= -2)],
                    base, "高开后回落≥2%(被兑现)"))
    print(summarize(feat[gap_up & feat["A_fri"]], base, "周五A+周一高开≥0.5%"))
    print(summarize(feat[gap_up & feat["A_fri"] & (feat["t1_oc"] < 0)], base,
                    "周五A+周一高开后收跌"))

    print("\n**A1. 按位置（60日累计涨幅）**\n")
    feat_base = feat  # 所有信号都在 feat 内
    for name, sig in (("A", "A"), ("A5", "A5")):
        print(f"\n*{name}*")
        print(HEADER)
        print(SEP)
        print(summarize(base, base, "基准"))
        for b in ["深跌<-30", "-30~-15", "-15~0", "0~15", "强势>15"]:
            s = feat[sig] & (feat["pos_bucket"] == b)
            if s.sum() >= 50:
                print(summarize(feat[s], base, b))

    print("\n**A2. 按量比 / 市场情绪 / 市值**\n")
    for title, col, order in (
            ("量比", "vol_bucket", ["1.5-2x", "2-3x", "3-5x", ">5x"]),
            ("市场涨停家数", "sent_bucket", ["冰点<30", "30-60", "60-100", "火热>100"]),
            ("流通市值", "mv_bucket", ["<50亿", "50-100亿", "100-300亿", ">=300亿"])):
        print(f"\n*A 按{title}*")
        print(HEADER)
        print(SEP)
        print(summarize(base, base, "基准"))
        for b in order:
            s = feat["A"] & (feat[col] == b)
            if s.sum() >= 50:
                print(summarize(feat[s], base, str(b)))

    print("\n**A3. 按星期（检验周五→周一是否特殊）**\n")
    print(HEADER)
    print(SEP)
    print(summarize(base, base, "基准"))
    for b in ["周一", "周二", "周三", "周四", "周五"]:
        s = feat["A"] & (feat["dow"] == b)
        if s.sum() >= 50:
            print(summarize(feat[s], base, b))

    print("\n**A4. 次日冲高回落之后，T+2 会怎样（二阶预期）**\n")
    print("| 分组 | 样本 | T+2均涨 | T+2胜率 | T+3均涨 | T+3胜率 |")
    print("|---|---|---|---|---|---|")
    for label, mask in (
            ("A 且 T+1冲高回落", feat["A"] & feat["t1_fade"]),
            ("A 且 T+1推动后收跌", feat["A"] & feat["t1_trap"]),
            ("A 且 T+1上涨", feat["A"] & feat["t1_up"]),
            ("A 且 T+1下跌", feat["A"] & ~feat["t1_up"]),
            ("A 且 T+1涨停", feat["A"] & (feat["f_pct"] >= feat["thr"])),
            ("周五A + 周一高开≥0.5%", feat["A_fri"] & (feat["t1_gap"] >= 0.5)),
            ("周五A + 周一高开后收跌",
             feat["A_fri"] & (feat["t1_gap"] >= 0.5) & (feat["t1_oc"] < 0)),
            ("基准", feat["t1_fade"])):
        s = feat[mask] if label != "基准" else base[base["t1_fade"]]
        s2 = s.dropna(subset=["t2_ret"])
        s3 = s.dropna(subset=["t3_ret"])
        if len(s2) == 0:
            continue
        print(f"| {label} | {len(s2)} | {s2['t2_ret'].mean():.2f}% | "
              f"{(s2['t2_ret']>0).mean()*100:.1f}% | "
              f"{s3['t3_ret'].mean():.2f}% | "
              f"{(s3['t3_ret']>0).mean()*100:.1f}% |")

    print("\n**A5. 指数级同步验证：上证放量上涨 → 次日**\n")
    idx = feat.drop_duplicates("date").dropna(subset=["idx_f_pct"]).copy()
    idx["idx_up"] = (idx["idx_pct"] >= 1.0) & (idx["idx_vol_ratio"] >= 1.2)
    for label, mask in (("上证涨≥1%+放量", idx["idx_up"]),
                        ("上证涨≥1.5%", idx["idx_pct"] >= 1.5),
                        ("基准", pd.Series(True, index=idx.index))):
        s = idx[mask]
        print(f"| {label} | {len(s)} | 次日均涨 {s['idx_f_pct'].mean():.2f}% | "
              f"胜率 {(s['idx_f_pct']>0).mean()*100:.1f}% |")

    print("\n**A7. 首板（当日涨停）特例：次日追高是否更容易被兑现**\n")
    fb = (feat["pct"] >= feat["thr"]) & (feat["prev_pct"] < feat["thr"])
    fb_gap = fb & (feat["t1_gap"] >= 0.5)
    fri = pd.to_datetime(feat["date"]).dt.dayofweek == 4
    print(HEADER)
    print(SEP)
    print(summarize(base, base, "基准"))
    print(summarize(feat[fb], base, "首板全部"))
    print(summarize(feat[fb_gap], base, "首板+次日高开≥0.5%"))
    print(summarize(feat[fb_gap & (~feat["t1_one_word"])], base,
                    "首板+次日高开(剔除一字)"))
    print(summarize(feat[fb_gap & (feat["t1_oc"] < 0)], base, "首板+高开后收跌"))
    print(summarize(feat[fb_gap & (feat["t1_close_from_high"] >= -0.5)],
                    base, "首板+高开收在最高"))
    print(summarize(feat[fb & fri & (feat["t1_gap"] >= 0.5)], base,
                    "周五首板+周一高开"))

    print("\n**A8. 追高后的持有成本（次日开盘买入 → T+2 收盘）**\n")
    print("| 分组 | 样本 | 开盘→T+1收 | 胜率 | 开盘→T+2收 | 胜率 |")
    print("|---|---|---|---|---|---|")
    for label, mask in (
            ("A 次日高开≥0.5%", gap_up),
            ("首板+次日高开", fb_gap & (~feat["t1_one_word"])),
            ("首板+高开后收跌", fb_gap & (feat["t1_oc"] < 0)),
            ("首板+高开收在最高", fb_gap & (feat["t1_close_from_high"] >= -0.5)),
            ("周五首板+周一高开", fb & fri & (feat["t1_gap"] >= 0.5))):
        s = feat[mask].dropna(subset=["t2_from_t1open"])
        if len(s) < 50:
            continue
        print(f"| {label} | {len(s)} | {s['t1_oc'].mean():.2f}% | "
              f"{(s['t1_oc']>0).mean()*100:.1f}% | "
              f"{s['t2_from_t1open'].mean():.2f}% | "
              f"{(s['t2_from_t1open']>0).mean()*100:.1f}% |")


def section_b(feat: pd.DataFrame, base: pd.DataFrame):
    print("\n" + "=" * 80)
    print("B. 连续下跌/放量恐慌 → 抛售之后资金反手买")
    print("=" * 80)
    feat = feat.copy()
    feat["b3"] = (feat["cum3"] <= -8) & (feat["vol_ratio"] >= 1.2)
    feat["b5"] = (feat["cum5"] <= -12) & (feat["vol_ratio"] >= 1.2)
    feat["b1"] = (feat["pct"] <= -6) & (feat["vol_ratio"] >= 1.2)
    feat["b3_shrink"] = (feat["cum3"] <= -8) & (feat["vol_ratio"] <= 0.8)
    feat["b3_capit"] = feat["b3"] & (feat["close_pos"] <= 0.2)
    feat["b3_offlow"] = feat["b3"] & (feat["close_pos"] >= 0.6)
    feat["b3_fri"] = feat["b3"] & (pd.to_datetime(feat["date"]).dt.dayofweek == 4)
    feat["pos_bucket"] = pd.cut(
        feat["cum60"], bins=[-np.inf, -30, -15, 0, 15, np.inf],
        labels=["深跌<-30", "-30~-15", "-15~0", "0~15", "强势>15"])
    feat["sent_bucket"] = pd.cut(
        feat["limit_up_cnt"], bins=[-np.inf, 30, 60, 100, np.inf],
        labels=["冰点<30", "30-60", "60-100", "火热>100"])

    print("\n**B0. 基准对照**\n")
    print("| 分组 | 样本 | T+1均涨 | T+1胜率 | T+2均涨 | T+2胜率 | T+3均涨 | T+3胜率 |")
    print("|---|---|---|---|---|---|---|---|")
    def row(label, s):
        s3 = s.dropna(subset=["t3_ret"])
        print(f"| {label} | {len(s)} | {s['t1_ret'].mean():.2f}% | "
              f"{(s['t1_ret']>0).mean()*100:.1f}% | {s['t2_ret'].mean():.2f}% | "
              f"{(s['t2_ret']>0).mean()*100:.1f}% | "
              f"{s3['t3_ret'].mean():.2f}% | {(s3['t3_ret']>0).mean()*100:.1f}% |")
    row("基准(全部)", base)
    for label, sig in (("B3 3日跌≥8%+放量1.2x", "b3"),
                       ("B5 5日跌≥12%+放量1.2x", "b5"),
                       ("B1 单日跌≥6%+放量1.2x", "b1"),
                       ("B3 缩量阴跌(量≤0.8x)", "b3_shrink"),
                       ("B3 收在最低20%(恐慌 capitulation)", "b3_capit"),
                       ("B3 收在最高60%(盘中已拉回)", "b3_offlow"),
                       ("B3 周五", "b3_fri")):
        s = feat[feat[sig]]
        if len(s) >= 50:
            row(label, s)

    print("\n**B0b. 周五恐慌：周五收盘状态决定周一**\n")
    print("| 分组 | 样本 | T+1均涨 | T+1胜率 | T+2均涨 | T+2胜率 | T+3均涨 | T+3胜率 |")
    print("|---|---|---|---|---|---|---|---|")
    for label, mask in (
            ("B3周五 收在最低20%", feat["b3_fri"] & (feat["close_pos"] <= 0.2)),
            ("B3周五 收在中间", feat["b3_fri"] & (feat["close_pos"] > 0.2)
             & (feat["close_pos"] < 0.6)),
            ("B3周五 盘中已拉回(收在最高60%)", feat["b3_fri"] & (feat["close_pos"] >= 0.6))):
        s = feat[mask]
        if len(s) >= 50:
            row(label, s)

    print("\n**B1. 按位置（60日累计涨幅）**\n")
    print("| 分组 | 样本 | T+1均涨 | T+1胜率 | T+2均涨 | T+2胜率 |")
    print("|---|---|---|---|---|---|")
    print(f"| 基准 | {len(base)} | {base['t1_ret'].mean():.2f}% | "
          f"{(base['t1_ret']>0).mean()*100:.1f}% | {base['t2_ret'].mean():.2f}% | "
          f"{(base['t2_ret']>0).mean()*100:.1f}% |")
    for b in ["深跌<-30", "-30~-15", "-15~0", "0~15", "强势>15"]:
        s = feat[feat["b3"] & (feat["pos_bucket"] == b)]
        if len(s) >= 50:
            print(f"| B3 {b} | {len(s)} | {s['t1_ret'].mean():.2f}% | "
                  f"{(s['t1_ret']>0).mean()*100:.1f}% | {s['t2_ret'].mean():.2f}% | "
                  f"{(s['t2_ret']>0).mean()*100:.1f}% |")

    print("\n**B2. 按市场情绪（涨停家数）**\n")
    print("| 分组 | 样本 | T+1均涨 | T+1胜率 | T+2均涨 | T+2胜率 |")
    print("|---|---|---|---|---|---|")
    print(f"| 基准 | {len(base)} | {base['t1_ret'].mean():.2f}% | "
          f"{(base['t1_ret']>0).mean()*100:.1f}% | {base['t2_ret'].mean():.2f}% | "
          f"{(base['t2_ret']>0).mean()*100:.1f}% |")
    for b in ["冰点<30", "30-60", "60-100", "火热>100"]:
        s = feat[feat["b3"] & (feat["sent_bucket"] == b)]
        if len(s) >= 50:
            print(f"| B3 {b}({s['date'].nunique()}d) | {len(s)} | "
                  f"{s['t1_ret'].mean():.2f}% | {(s['t1_ret']>0).mean()*100:.1f}% | "
                  f"{s['t2_ret'].mean():.2f}% | {(s['t2_ret']>0).mean()*100:.1f}% |")

    print("\n**B3. 恐慌之后：反弹是否延续（二阶）**\n")
    print("| 分组 | 样本 | T+2均涨 | T+2胜率 | 说明 |")
    print("|---|---|---|---|")
    for label, mask, note in (
            ("B3 且 T+1反弹", feat["b3"] & feat["t1_up"], "反弹首日追入"),
            ("B3 且 T+1继续跌", feat["b3"] & ~feat["t1_up"], "接飞刀"),
            ("B3 且 T+1缩量(≤0.7x)", feat["b3"] & (feat["f_volume"] <= feat["volume"] * 0.7),
             "放量下跌后缩量(对应 F-008)"),
            ("B3 且 T+1放量", feat["b3"] & (feat["f_volume"] >= feat["volume"] * 1.2),
             "恐慌延续")):
        s = feat[mask].dropna(subset=["t2_ret"])
        if len(s) >= 50:
            print(f"| {label} | {len(s)} | {s['t2_ret'].mean():.2f}% | "
                  f"{(s['t2_ret']>0).mean()*100:.1f}% | {note} |")

    print("\n**B4. 从恐慌日收盘买入的累计收益**\n")
    print("| 分组 | 样本 | T+1 | T+2累计 | T+3累计 | T+3胜率 |")
    print("|---|---|---|---|---|---|")
    for label, mask in (
            ("基准", pd.Series(True, index=feat.index)),
            ("B3 放量恐慌", feat["b3"]),
            ("B3 收在最低20%", feat["b3_capit"]),
            ("B3 盘中已拉回", feat["b3_offlow"]),
            ("B3 缩量阴跌", feat["b3_shrink"]),
            ("B3 周五", feat["b3_fri"]),
            ("B3 周五收最低", feat["b3_fri"] & (feat["close_pos"] <= 0.2)),
            ("B3 冰点<30", feat["b3"] & (feat["sent_bucket"] == "冰点<30")),
            ("B3 30-60", feat["b3"] & (feat["sent_bucket"] == "30-60")),
            ("B3 火热>100", feat["b3"] & (feat["sent_bucket"] == "火热>100"))):
        s = feat[mask].dropna(subset=["t3_from_t"])
        if len(s) < 50:
            continue
        print(f"| {label} | {len(s)} | {s['t1_ret'].mean():.2f}% | "
              f"{s['t2_from_t'].mean():.2f}% | {s['t3_from_t'].mean():.2f}% | "
              f"{(s['t3_from_t']>0).mean()*100:.1f}% |")

    print("\n**B5. 市场级：上证连续下跌 → 次日**\n")
    idx = feat.drop_duplicates("date").dropna(
        subset=["idx_f_pct", "idx_cum3_prev"]).copy()
    for label, mask in (
            ("上证前3日累计≤-2.5%", idx["idx_cum3_prev"] <= -2.5),
            ("上证前5日累计≤-4%", idx["idx_cum5_prev"] <= -4),
            ("上证单日≤-1.5%", idx["idx_pct"] <= -1.5),
            ("基准", pd.Series(True, index=idx.index))):
        s = idx[mask]
        if len(s) >= 10:
            print(f"| {label} | {len(s)} | 次日均涨 {s['idx_f_pct'].mean():.2f}% | "
                  f"胜率 {(s['idx_f_pct']>0).mean()*100:.1f}% |")


def monthly_by_friday(feat: pd.DataFrame, base: pd.DataFrame):
    """看 A 信号在不同月份的稳定性（防止单一区间结论）。"""
    print("\n**A6. A 信号月度稳定性（T+1 均涨 / 冲高回落率）**\n")
    print("| 月份 | 样本 | 交易日 | T+1均涨 | 冲高回落 | T+2均涨 |")
    print("|---|---|---|---|---|---|")
    a = feat[(feat["pct"] >= 3) & (feat["pct"] < feat["thr"])
             & (feat["vol_ratio"] >= 1.5)].copy()
    a["month"] = pd.to_datetime(a["date"]).dt.to_period("M").astype(str)
    for m, s in a.groupby("month"):
        if len(s) < 50:
            continue
        print(f"| {m} | {len(s)} | {s['date'].nunique()} | {s['t1_ret'].mean():.2f}% | "
              f"{s['t1_fade'].mean()*100:.1f}% | {s['t2_ret'].mean():.2f}% |")


def run_daily():
    conn = get_conn()
    df = load_daily(conn)
    idx_df = load_index(conn)
    conn.close()
    print(f"加载日K {len(df)} 行，指数 {len(idx_df)} 行")
    feat = build_features(df, idx_df)

    valid = feat[(feat["volume"] > 0) & feat["pct"].notna() & feat["ok_t1"]
                 & (feat["f_open"] > 0) & (feat["f_close"] > 0)].copy()
    main = valid[(valid["mv_latest"].notna()) & (valid["mv_latest"] < 300)]
    print(f"有效样本 {len(valid)} 行；<300亿主样本 {len(main)} 行")

    section_a(main, main)
    section_b(main, main)
    monthly_by_friday(main, main)

    # 全市场（不过滤市值）对照核心结论
    print("\n" + "=" * 80)
    print("C. 全市场（不过滤市值）对照")
    print("=" * 80)
    a = (valid["pct"] >= 3) & (valid["pct"] < valid["thr"]) & (valid["vol_ratio"] >= 1.5)
    b3 = (valid["cum3"] <= -8) & (valid["vol_ratio"] >= 1.2)
    print(f"全市场基准 T+1 均涨 {valid['t1_ret'].mean():.2f}% / 胜率 "
          f"{(valid['t1_ret']>0).mean()*100:.1f}%")
    print(f"A 全市场: n={a.sum()} T+1 {valid[a]['t1_ret'].mean():.2f}% / "
          f"冲高回落 {valid[a]['t1_fade'].mean()*100:.1f}% / "
          f"T+1开→收 {valid[a]['t1_oc'].mean():.2f}%")
    print(f"B3 全市场: n={b3.sum()} T+1 {valid[b3]['t1_ret'].mean():.2f}% / "
          f"T+2 {valid[b3]['t2_ret'].mean():.2f}% / "
          f"T+1胜率 {(valid[b3]['t1_ret']>0).mean()*100:.1f}%")


def run_intraday():
    conn = get_conn()
    print("加载上证1分钟…")
    im = query_df(conn, """
        SELECT ts, open, high, low, close, volume
        FROM index_minute
        WHERE code='sh000001' AND freq='1m'
        ORDER BY ts
    """)
    im["ts"] = pd.to_datetime(im["ts"])
    im["d"] = im["ts"].dt.date
    im["t"] = im["ts"].dt.time

    idx = load_index(conn)
    conn.close()

    rows = []
    for d, g in im.groupby("d"):
        g = g.sort_values("ts")
        o930 = g.iloc[0]["open"]
        pre = g[g["t"] <= pd.Timestamp("10:00").time()]
        if pre.empty:
            continue
        c1000 = pre.iloc[-1]["close"]
        c1500 = g.iloc[-1]["close"]
        rows.append((d, o930, c1000, c1500))
    intra = pd.DataFrame(rows, columns=["date", "o930", "c1000", "c1500"])
    intra["first30"] = (intra["c1000"] / intra["o930"] - 1) * 100
    intra["rest"] = (intra["c1500"] / intra["c1000"] - 1) * 100
    intra["day"] = (intra["c1500"] / intra["o930"] - 1) * 100

    idx = idx.copy()
    idx["idx_cum3_prev"] = idx["pct"].shift(1).rolling(3).sum()
    idx["idx_cum5_prev"] = idx["pct"].shift(1).rolling(5).sum()
    intra = intra.merge(idx[["date", "pct", "idx_cum3_prev", "idx_cum5_prev"]],
                        on="date", how="left")
    print(f"指数分钟覆盖 {intra['date'].min()} ~ {intra['date'].max()}，"
          f"{len(intra)} 个交易日")

    print("\n**D1. 上午10点前下跌 → 10点后资金是否反手买（上证）**\n")
    print("| 条件 | 样本 | 10点后均涨 | 10点后胜率 | 全天均涨 | 全天胜率 |")
    print("|---|---|---|---|---|---|")
    for label, mask in (
            ("全部", pd.Series(True, index=intra.index)),
            ("10点前跌≤-0.3%", intra["first30"] <= -0.3),
            ("10点前跌≤-0.5%", intra["first30"] <= -0.5),
            ("10点前跌≤-0.8%", intra["first30"] <= -0.8),
            ("前3日跌≤-1.5% + 10点前跌≤-0.3%",
             (intra["idx_cum3_prev"] <= -1.5) & (intra["first30"] <= -0.3)),
            ("前3日跌≤-1.5% + 10点前跌≤-0.5%",
             (intra["idx_cum3_prev"] <= -1.5) & (intra["first30"] <= -0.5)),
            ("前5日跌≤-2.5% + 10点前跌≤-0.5%",
             (intra["idx_cum5_prev"] <= -2.5) & (intra["first30"] <= -0.5)),
            ("前3日涨≥1.5% + 10点前涨≥0.3%（反例：强势追高）",
             (intra["idx_cum3_prev"] >= 1.5) & (intra["first30"] >= 0.3))):
        s = intra[mask]
        if len(s) < 5:
            continue
        print(f"| {label} | {len(s)} | {s['rest'].mean():.2f}% | "
              f"{(s['rest']>0).mean()*100:.1f}% | {s['day'].mean():.2f}% | "
              f"{(s['day']>0).mean()*100:.1f}% |")

    print("\n**D2. 2026-10-23（用户举例的周五）逐段复盘**\n")
    row = intra[intra["date"] == pd.Timestamp("2026-10-23").date()]
    if not row.empty:
        r = row.iloc[0]
        print(f"9:30开 {r['o930']:.2f} → 10:00 {r['c1000']:.2f} "
              f"（{r['first30']:+.2f}%）→ 收盘 {r['c1500']:.2f}"
              f"（10点后 {r['rest']:+.2f}%，全天 {r['day']:+.2f}%）")

    # 个股级：最近12个交易日
    print("\n**D3. 个股级：10点前跌≥2% + 前3日跌≥5% → 10点后（仅10/08~10/23）**\n")
    conn = get_conn()
    try:
        sm = query_df(conn, """
            SELECT code, ts::date AS d,
                   min(open) FILTER (WHERE ts::time = TIME '09:30') AS o930,
                   min(price) FILTER (WHERE ts::time = TIME '10:00') AS c1000,
                   min(price) FILTER (WHERE ts::time = TIME '15:00') AS c1500
            FROM stock_minute
            WHERE freq='1m' AND (code LIKE 'sh6%' OR code LIKE 'sz0%'
                  OR code LIKE 'sz30%' OR code LIKE 'sh68%')
            GROUP BY code, ts::date
        """)
    except Exception as e:  # noqa: BLE001
        print("SQL 聚合失败：", e)
        conn.close()
        return
    conn.close()
    sm["d"] = pd.to_datetime(sm["d"]).dt.date
    sm = sm.dropna()
    sm["first30"] = (sm["c1000"] / sm["o930"] - 1) * 100
    sm["rest"] = (sm["c1500"] / sm["c1000"] - 1) * 100
    conn = get_conn()
    df = load_daily(conn)
    conn.close()
    df = df.sort_values(["code", "date"])
    df["cum3_prev"] = df.groupby("code")["pct"].transform(
        lambda s: s.shift(1).rolling(3, min_periods=3).sum())
    sm = sm.merge(df[["code", "date", "cum3_prev", "circ_mv"]],
                  left_on=["code", "d"], right_on=["code", "date"], how="left")
    sm = sm[sm["circ_mv"].fillna(9999) < 300]
    print("| 条件 | 样本 | 10点后均涨 | 10点后胜率 | 说明 |")
    print("|---|---|---|---|---|")
    for label, mask, note in (
            ("全部", pd.Series(True, index=sm.index), "近12日"),
            ("10点前跌≥2%", sm["first30"] <= -2, "日内恐慌"),
            ("10点前跌≥2% + 前3日跌≥5%", (sm["first30"] <= -2) & (sm["cum3_prev"] <= -5),
             "连续下跌后再恐慌"),
            ("10点前涨≥2%（反例）", sm["first30"] >= 2, "追高对照")):
        s = sm[mask]
        if len(s) < 20:
            continue
        print(f"| {label} | {len(s)} | {s['rest'].mean():.2f}% | "
              f"{(s['rest']>0).mean()*100:.1f}% | {note} |")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "daily"
    if mode == "daily":
        run_daily()
    elif mode == "intraday":
        run_intraday()
    else:
        print("用法: backtest_expectation.py [daily|intraday]")
