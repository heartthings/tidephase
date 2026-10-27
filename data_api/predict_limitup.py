#!/usr/bin/env python3
"""
次日首板 / 二板预测引擎

给每日收盘简报用：基于 stock_daily 历史（2025-09 起），用可解释特征的
L2 逻辑回归分别估计
  - 明日首板概率：今日未涨停的股票，明日涨停的概率
  - 明日二板概率：今日首板的股票，明日继续涨停的概率

口径与既有回测一致：
  - 涨停阈值：ST 4.8 / sz30·sh68 19.8 / 其余 9.8
  - 主样本：沪深 A 股、流通市值 < 300 亿。有逐日 circ_mv 的日子用当天的；
    更早的日子只用该股第一次观测到的流通市值，不用之后更新的值
  - 标签与特征均按相邻交易日计算；停牌/无量的 T+1 不计入
  - 题材用开盘啦 stock_sector_map（801 开头），按当天有效区间取值，不用之后才出现的归属。
    父子板块来自开盘啦 SonPlate：股票落在子板块上写成「父 / 分支」
  - 首板候选不选过往龙头。只留：前期缩量后连续放量，或急跌之后，
    并且放量上影还在放大，同时落在风口题材上

不依赖 sklearn：numpy 手写 Adam + 标准化，概率由逻辑回归直接给出。

对外主入口：
  predict(conn, target_date=None, top_first=15, top_second=10) -> dict
  render_markdown(result) -> str
"""
from __future__ import annotations

import json
import math
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import psycopg2
import psycopg2.extras
import yaml

SECRETS_PATH = Path(__file__).resolve().parent.parent / "configs" / "secrets.yaml"

FEATURES = [
    "pct", "vol_ratio5", "close_pos", "upper_shadow", "gap_open", "amp",
    "cum3", "cum10", "cum20", "cum60",
    "dist_hi60", "dist_lo60", "log_circ", "is_20cm", "is_sealed",
    "recent_zt20", "mkt_lu", "mkt_ld", "mkt_height", "idx_pct",
    "theme_zt", "theme_zt3", "theme_height",
]
FEATURE_CN = {
    "pct": "当日涨幅", "vol_ratio5": "量比(5日)", "close_pos": "收盘位置",
    "upper_shadow": "上影线", "gap_open": "跳空", "amp": "振幅",
    "cum3": "3日累计", "cum10": "10日累计", "cum20": "20日累计", "cum60": "60日累计",
    "dist_hi60": "距60日高", "dist_lo60": "距60日低", "log_circ": "流通市值",
    "is_20cm": "20cm", "is_sealed": "收在最高",
    "recent_zt20": "20日涨停次数", "mkt_lu": "全市场涨停数", "mkt_ld": "全市场跌停数",
    "mkt_height": "市场最高板", "idx_pct": "上证涨幅",
    "theme_zt": "题材今日涨停数", "theme_zt3": "题材3日涨停数", "theme_height": "题材最高板",
}


# ─────────────────────────── 数据 ───────────────────────────

def get_conn():
    password = os.getenv("MARKET_TSDB_READER_PASSWORD", "")
    if not password and SECRETS_PATH.exists():
        with open(SECRETS_PATH) as f:
            conf = yaml.safe_load(f) or {}
        password = conf.get("database", {}).get("duser_reader_password", "")
    return psycopg2.connect(
        host=os.getenv("MARKET_TSDB_HOST", "127.0.0.1"),
        port=int(os.getenv("MARKET_TSDB_PORT", "15432")),
        dbname=os.getenv("MARKET_TSDB_NAME", "market_tsdb"),
        user=os.getenv("MARKET_TSDB_USER_READER", "duser_reader"),
        password=password,
    )


def _query(conn, sql: str, params=None) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute(sql, params or [])
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
    return pd.DataFrame(rows, columns=cols)


def load_history(conn, start: str) -> pd.DataFrame:
    df = _query(conn, """
        SELECT date, code, name, open, high, low, close, pct, volume, amount, circ_mv,
               is_st, is_suspended
        FROM stock_daily
        WHERE date >= %s AND (code LIKE 'sh%%' OR code LIKE 'sz%%') AND close > 0
        ORDER BY code, date
    """, [start])
    df["date"] = pd.to_datetime(df["date"]).dt.date
    for c in ("open", "high", "low", "close", "pct", "volume"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def load_index(conn, start: str) -> pd.DataFrame:
    df = _query(conn, """
        SELECT date, pct, close FROM index_daily
        WHERE code = 'sh000001' AND date >= %s ORDER BY date
    """, [start])
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["pct"] = pd.to_numeric(df["pct"], errors="coerce")
    return df


def load_themes(conn) -> pd.DataFrame:
    df = _query(conn, """
        SELECT code, sector_code, sector_name, effective_from, effective_to
        FROM stock_sector_map
        WHERE kind = 'theme' AND sector_code LIKE '801%%'
    """)
    if df.empty:
        return df
    df["effective_from"] = pd.to_datetime(df["effective_from"]).dt.date
    df["effective_to"] = pd.to_datetime(df["effective_to"]).dt.date
    return df


def themes_on(themes: pd.DataFrame, d: date) -> pd.DataFrame:
    """当天已经生效、还没被关掉的开盘啦归属。之后才写入的映射不往回用。"""
    if themes.empty:
        return themes
    et = themes["effective_to"]
    m = themes[(themes["effective_from"] <= d) & (et.isna() | (et > d))]
    return m.drop_duplicates(["code", "sector_code"])


def load_zt_today(conn, d: date) -> pd.DataFrame:
    return _query(conn, """
        SELECT code, name, close, pct, board_days, first_seal_time, seal_amount,
               break_times, theme, reason, circ_mv, turnover_rate
        FROM zt_pool WHERE date = %s
    """, [d])


def load_zb_today(conn, d: date) -> pd.DataFrame:
    return _query(conn, """
        SELECT code, name, pct, break_times FROM zb_pool WHERE date = %s
    """, [d])


def load_dt_today(conn, d: date) -> pd.DataFrame:
    return _query(conn, "SELECT code, name FROM dt_pool WHERE date = %s", [d])


def load_fund_today(conn, d: date) -> pd.DataFrame:
    return _query(conn, """
        SELECT code, main_net_inflow, main_net_pct FROM fund_flow_stock WHERE date = %s
    """, [d])


# ─────────────────────────── 特征 ───────────────────────────

def _thr(code: str, is_st) -> float:
    if is_st is True or is_st == 1:
        return 4.8
    if code.startswith(("sz30", "sh68")):
        return 19.8
    return 9.8


def build_features(df: pd.DataFrame, idx: pd.DataFrame, themes: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["code", "date"]).reset_index(drop=True)
    df["thr"] = [_thr(c, s) for c, s in zip(df["code"], df["is_st"])]
    df["is_lu"] = df["pct"] >= df["thr"]
    df["is_ld"] = df["pct"] <= -df["thr"] + 0.2

    g = df.groupby("code", sort=False)
    df["prev_lu"] = g["is_lu"].shift(1).fillna(False).astype(bool)
    df["prev2_lu"] = g["is_lu"].shift(2).fillna(False).astype(bool)
    df["is_first"] = df["is_lu"] & (~df["prev_lu"])

    s = df["is_lu"].astype(np.int8)
    block = (s == 0).groupby(df["code"]).cumsum()
    df["board_days"] = s.groupby([df["code"], block]).cumsum().astype(int)

    df["vol_ma5"] = g["volume"].transform(
        lambda x: x.shift(1).rolling(5, min_periods=5).mean())
    df["vol_ratio5"] = df["volume"] / df["vol_ma5"]
    for w in (3, 10, 20, 60):
        df[f"cum{w}"] = g["pct"].transform(
            lambda x, w=w: x.rolling(w, min_periods=w).sum())
    df["hi60"] = g["high"].transform(lambda x: x.rolling(60, min_periods=60).max())
    df["lo60"] = g["low"].transform(lambda x: x.rolling(60, min_periods=60).min())
    df["recent_zt20"] = g["is_lu"].transform(
        lambda x: x.shift(1).rolling(20, min_periods=20).sum())

    rng = (df["high"] - df["low"]).replace(0, np.nan)
    df["close_pos"] = ((df["close"] - df["low"]) / rng).fillna(1.0)
    df["upper_shadow"] = (df["high"] - df["close"]) / df["close"] * 100
    df["amp"] = (df["high"] - df["low"]) / df["close"] * 100
    df["gap_open"] = (df["open"] / g["close"].shift(1) - 1) * 100
    df["dist_hi60"] = (df["close"] / df["hi60"] - 1) * 100
    df["dist_lo60"] = (df["close"] / df["lo60"] - 1) * 100
    df["is_20cm"] = df["code"].str.startswith(("sz30", "sh68")).astype(int)
    df["is_sealed"] = (df["close"] >= df["high"] - 1e-6).astype(int)

    # 流通市值：当天有值用当天。前面的空档只用该股第一次观测值，不用更晚的值。
    obs = df["circ_mv"].where(df["circ_mv"] > 0)
    filled = obs.groupby(df["code"]).ffill()
    first_map = df.loc[obs.notna()].groupby("code")["circ_mv"].first()
    df["mv"] = filled.fillna(df["code"].map(first_map))
    df["log_circ"] = np.log(df["mv"].clip(lower=1))

    v1 = g["volume"].shift(1)
    v2 = g["volume"].shift(2)
    vol_quiet = g["volume"].transform(lambda x: x.shift(6).rolling(15, min_periods=10).mean())
    vol_base = g["volume"].transform(lambda x: x.shift(21).rolling(20, min_periods=15).mean())
    df["shrink"] = vol_quiet < vol_base * 0.75
    df["burst3"] = (df["volume"] > v1) & (v1 > v2) & (df["volume"] > vol_quiet * 1.5)
    df["crash"] = df["cum3"] <= -8
    df["shadow_cont"] = (
        (df["upper_shadow"] > 2) & (df["vol_ratio5"] >= 1.5) & (df["volume"] > v1)
    )
    max_board60 = g["board_days"].transform(
        lambda x: x.shift(1).rolling(60, min_periods=1).max())
    df["old_dragon"] = (df["recent_zt20"].fillna(0) >= 2) | (max_board60.fillna(0) >= 3)
    df["pattern_ok"] = (
        (~df["old_dragon"].fillna(False))
        & df["shadow_cont"].fillna(False)
        & (
            (df["shrink"].fillna(False) & df["burst3"].fillna(False))
            | df["crash"].fillna(False)
        )
    )
    df["pattern_kind"] = ""
    crash_hit = df["pattern_ok"] & df["crash"].fillna(False)
    shrink_hit = df["pattern_ok"] & ~crash_hit
    df.loc[crash_hit, "pattern_kind"] = "急跌后放量上影"
    df.loc[shrink_hit, "pattern_kind"] = "缩量后连续放量上影"

    # 市场宽度
    mkt = df.groupby("date").agg(
        mkt_lu=("is_lu", "sum"), mkt_ld=("is_ld", "sum"),
        mkt_height=("board_days", "max")).reset_index()
    mkt["mkt_lu"] = np.log1p(mkt["mkt_lu"])
    mkt["mkt_ld"] = np.log1p(mkt["mkt_ld"])
    df = df.merge(mkt, on="date", how="left")
    df = df.merge(idx[["date", "pct"]].rename(columns={"pct": "idx_pct"}),
                  on="date", how="left")
    df["idx_pct"] = df["idx_pct"].fillna(0)

    # 题材热度
    df = _attach_theme_stats(df, themes)

    # 前向标签
    g = df.groupby("code", sort=False)
    df["next_lu"] = g["is_lu"].shift(-1)
    df["next_ok"] = g["volume"].shift(-1).fillna(0) > 0
    df["next_ok"] &= g["open"].shift(-1).fillna(0) > 0
    df["next_ok"] &= g["close"].shift(-1).fillna(0) > 0
    return df


def _attach_theme_stats(df: pd.DataFrame, themes: pd.DataFrame) -> pd.DataFrame:
    """题材热度按当天有效归属计算。映射开始之前的日子记 0，避免用后来的标签。"""
    if themes.empty:
        for c in ("theme_zt", "theme_zt3", "theme_height"):
            df[c] = 0.0
        df["theme_name"] = ""
        df["theme_code"] = ""
        return df

    map_start = themes["effective_from"].min()
    dates = [d for d in sorted(df["date"].unique()) if d >= map_start]
    lu = df.loc[df["is_lu"], ["date", "code", "board_days"]]
    pieces = []
    zt_hist: Dict[str, List[tuple]] = {}
    for d in dates:
        mem = themes_on(themes, d)
        if mem.empty:
            continue
        name_of = (mem.drop_duplicates("sector_code")
                   .set_index("sector_code")["sector_name"])
        day_lu = lu[lu["date"] == d]
        zt_map: Dict[str, int] = {}
        ht_map: Dict[str, int] = {}
        if len(day_lu):
            td = day_lu.merge(mem[["code", "sector_code"]], on="code", how="inner")
            if len(td):
                agg = td.groupby("sector_code").agg(
                    zt=("code", "nunique"), height=("board_days", "max"))
                zt_map = {k: int(v) for k, v in agg["zt"].items()}
                ht_map = {k: int(v) for k, v in agg["height"].items()}
        for sec, zt in zt_map.items():
            zt_hist.setdefault(sec, []).append((d, zt, ht_map.get(sec, 0)))
        codes = df.loc[df["date"] == d, ["date", "code"]]
        m = codes.merge(mem[["code", "sector_code"]], on="code", how="left")
        m["theme_zt"] = m["sector_code"].map(zt_map).fillna(0.0)
        m["theme_height"] = m["sector_code"].map(ht_map).fillna(0.0)
        m["theme_name"] = m["sector_code"].map(name_of).fillna("")
        m["theme_code"] = m["sector_code"].fillna("")
        m = m.sort_values(["date", "code", "theme_zt"], ascending=[True, True, False])
        pieces.append(m.groupby(["date", "code"], as_index=False).first()[
            ["date", "code", "theme_zt", "theme_height", "theme_name", "theme_code"]])
    if not pieces:
        for c in ("theme_zt", "theme_height"):
            df[c] = 0.0
        df["theme_name"] = ""
        df["theme_code"] = ""
        df["theme_zt3"] = 0.0
        return df
    out = pd.concat(pieces, ignore_index=True)
    zt3 = {}
    for sec, seq in zt_hist.items():
        seq = sorted(seq)
        window = []
        for d, zt, _h in seq:
            window.append(zt)
            zt3[(d, sec)] = float(sum(window[-3:]))
    out["theme_zt3"] = [
        zt3.get((d, c), 0.0) for d, c in zip(out["date"], out["theme_code"])
    ]
    return df.merge(
        out[["date", "code", "theme_zt", "theme_zt3", "theme_height",
             "theme_name", "theme_code"]],
        on=["date", "code"], how="left",
    ).fillna({"theme_zt": 0.0, "theme_zt3": 0.0, "theme_height": 0.0,
              "theme_name": "", "theme_code": ""})


HOT_PHASES = {"聚集未完成", "启动期", "发酵期", "高潮期"}
# 这些是身份或事件标签，涨停家数会很大，但不能当成舞台本身。
POCKET_THEMES = {
    "业绩增长", "中报增长", "三季报增长", "年报增长", "预盈预增",
    "股权转让", "国有企业", "地方国企", "央企", "国企改革", "央国企改革",
    "超跌", "低价股", "沪股通", "深股通", "融资融券", "证金持股",
}
PLATE_CACHE = Path(__file__).resolve().parent.parent / "data" / "cache" / "kpl_plate_tree.json"


def load_plate_tree(parents: Optional[dict] = None) -> dict:
    """开盘啦子板块。child_code -> {parent_code, parent_name, child_name}。

    缓存 20 小时。接口失败时用已有缓存，没有缓存就返回空，不编父子关系。
    """
    import time
    cached = None
    if PLATE_CACHE.exists():
        try:
            cached = json.loads(PLATE_CACHE.read_text())
        except Exception:
            cached = None
        if cached and time.time() - PLATE_CACHE.stat().st_mtime < 20 * 3600:
            return cached.get("children") or {}
    try:
        fresh = _fetch_plate_tree(parents or {})
    except Exception:
        fresh = None
    if fresh:
        PLATE_CACHE.parent.mkdir(parents=True, exist_ok=True)
        PLATE_CACHE.write_text(json.dumps({"children": fresh}, ensure_ascii=False))
        return fresh
    return (cached or {}).get("children") or {}


def _fetch_plate_tree(parents: dict) -> dict:
    import requests
    from concurrent.futures import ThreadPoolExecutor, as_completed
    conf = yaml.safe_load(SECRETS_PATH.read_text()) if SECRETS_PATH.exists() else {}
    lh = conf.get("longhu") or {}
    device = ((lh.get("account_3167791") or {}).get("device_id")) or ""
    host = (lh.get("hosts") or {}).get("apphwhq") or "https://apphwhq.longhuvip.com/w1/api/index.php"
    headers = {
        "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 12)",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    }
    parent_name = {str(k): v for k, v in (parents or {}).items() if str(k).startswith("80")}

    def one(code: str):
        try:
            resp = requests.post(host, data={
                "a": "SonPlate_Info", "c": "ZhiShuRanking",
                "PhoneOSNew": "1", "VerSion": "5.21.0.0", "apiv": "w42",
                "DeviceID": device, "PlateID": code,
            }, headers=headers, timeout=12)
            data = resp.json()
        except Exception:
            return code, []
        if str(data.get("errcode", "0")) not in ("0", ""):
            return code, []
        kids = []
        raw = data.get("List") or data.get("list") or []
        for item in raw:
            if isinstance(item, list) and len(item) >= 2 and str(item[0]).startswith("80"):
                kids.append((str(item[0]), str(item[1])))
        return code, kids

    children = {}
    codes = list(parent_name)
    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = [pool.submit(one, c) for c in codes]
        for fut in as_completed(futs):
            parent, kids = fut.result()
            for child, child_name in kids:
                # 一个分支只挂到先看到的父题材上；展示时若股票同时属于多个父，再按当天涨停选
                children.setdefault(child, {
                    "parent_code": parent,
                    "parent_name": parent_name.get(parent) or parent,
                    "child_name": child_name,
                })
    return children


def _pick_theme(codes_themes: pd.DataFrame, stats: dict, tree: dict) -> dict:
    """在这只股票的开盘啦标签里，优先当天有涨停的分支，而不是更宽的父题材。"""
    best = {"theme": "", "theme_code": "", "role": "", "parent": "",
            "zt": 0, "height": 0, "phase": "无涨停", "zt3": []}
    if codes_themes is None or len(codes_themes) == 0:
        return best
    rows = []
    for _, r in codes_themes.iterrows():
        sec = str(r["sector_code"])
        st = stats.get(sec) or {}
        info = tree.get(sec) or {}
        rows.append({
            "code": sec,
            "name": st.get("name") or r["sector_name"] or info.get("child_name") or "",
            "zt": int(st.get("zt") or 0),
            "height": int(st.get("height") or 0),
            "phase": st.get("phase") or "无涨停",
            "zt3": st.get("zt3") or [],
            "is_child": sec in tree,
            "parent_name": info.get("parent_name") or "",
            "parent_code": info.get("parent_code") or "",
        })
    def _rank(x):
        pocket = 0 if x["name"] in POCKET_THEMES else 1
        return (pocket, 1 if x["is_child"] else 0, x["zt"], x["height"])

    hot_children = [x for x in rows if x["is_child"] and x["zt"] > 0 and x["name"] not in POCKET_THEMES]
    if hot_children:
        chosen = max(hot_children, key=_rank)
        label = f"{chosen['parent_name']} / {chosen['name']}" if chosen["parent_name"] else chosen["name"]
        return {**best, "theme": label, "theme_code": chosen["code"], "role": "分支",
                "parent": chosen["parent_name"], "zt": chosen["zt"],
                "height": chosen["height"], "phase": chosen["phase"], "zt3": chosen["zt3"]}
    alive = [x for x in rows if x["zt"] > 0 and x["name"] not in POCKET_THEMES]
    pool = alive or [x for x in rows if x["zt"] > 0] or rows
    chosen = max(pool, key=_rank)
    role = ""
    parent = ""
    child_parents = {info["parent_code"] for info in tree.values()}
    if chosen["code"] in child_parents and not chosen["is_child"]:
        role = "父题材"
        parent = chosen["name"]
        label = f"{chosen['name']}（父题材）"
    else:
        label = chosen["name"]
    return {**best, "theme": label, "theme_code": chosen["code"], "role": role,
            "parent": parent, "zt": chosen["zt"], "height": chosen["height"],
            "phase": chosen["phase"], "zt3": chosen["zt3"]}


def _sector_stats(df: pd.DataFrame, mem: pd.DataFrame, d: date,
                  prev: Optional[date], zb_today: pd.DataFrame,
                  zb_prev: pd.DataFrame) -> dict:
    """每个开盘啦板块当天的涨停、严格连板高度、炸板和阶段。"""
    if mem.empty:
        return {}
    name_of = (mem.drop_duplicates("sector_code")
               .set_index("sector_code")["sector_name"].to_dict())
    dates = sorted(df["date"].unique())
    hist_dates = [x for x in dates if x <= d][-3:]
    lu = df.loc[df["is_lu"] & df["date"].isin(hist_dates), ["date", "code", "board_days"]]
    td = lu.merge(mem[["code", "sector_code"]], on="code", how="inner")
    by_sec: Dict[str, dict] = {}
    for sec, name in name_of.items():
        by_sec[sec] = {"name": name, "zt": 0, "height": 0, "zt3": [],
                       "broken": 0, "broken_prev": 0, "high_broken": False, "phase": "无涨停"}
    if len(td):
        for day, g in td.groupby("date"):
            agg = g.groupby("sector_code").agg(zt=("code", "nunique"), height=("board_days", "max"))
            for sec, row in agg.iterrows():
                node = by_sec.get(sec)
                if node is None:
                    continue
                if day == d:
                    node["zt"] = int(row["zt"])
                    node["height"] = int(row["height"])
                node["zt3"].append(int(row["zt"]))
    # 高位断板：昨天严格连板 >= 4，今天没涨停
    if prev is not None:
        y = df[(df["date"] == prev) & (df["board_days"] >= 4)][["code", "board_days"]]
        today_lu = set(df.loc[(df["date"] == d) & df["is_lu"], "code"])
        broken_codes = set(y.loc[~y["code"].isin(today_lu), "code"])
        if broken_codes:
            hit = mem[mem["code"].isin(broken_codes)]["sector_code"].unique()
            for sec in hit:
                if sec in by_sec:
                    by_sec[sec]["high_broken"] = True
    def _broken(pool, key):
        if pool is None or len(pool) == 0:
            return
        codes = set(pool["code"])
        hit = mem[mem["code"].isin(codes)].groupby("sector_code")["code"].nunique()
        for sec, n in hit.items():
            if sec in by_sec:
                by_sec[sec][key] = int(n)
    _broken(zb_today, "broken")
    _broken(zb_prev, "broken_prev")
    for node in by_sec.values():
        node["phase"] = _phase(node["zt"], node["zt3"], node["height"],
                               node["broken"], node["broken_prev"], node["high_broken"])
    return by_sec


# ─────────────────────────── 模型 ───────────────────────────

class Logistic:
    def __init__(self):
        self.mu = None
        self.sd = None
        self.w = None
        self.b = 0.0
        self.calib: Optional[Tuple[float, float]] = None
        self.iso: Optional[Tuple[np.ndarray, np.ndarray]] = None
        self.rank_table: Optional[List[dict]] = None

    def fit(self, X: np.ndarray, y: np.ndarray, l2: float = 1e-3,
            epochs: int = 26, lr: float = 0.05, batch: int = 65536):
        X = X.astype(np.float32)
        self.mu = np.nan_to_num(X.mean(axis=0), nan=0.0, posinf=0.0, neginf=0.0)
        self.sd = np.nan_to_num(X.std(axis=0), nan=1.0, posinf=1.0, neginf=1.0)
        self.sd[self.sd < 1e-8] = 1.0
        Z = (X - self.mu) / self.sd
        n, d = Z.shape
        rng = np.random.default_rng(42)
        self.w = np.zeros(d, dtype=np.float32)
        self.b = float(np.log(max(y.mean(), 1e-6) / max(1 - y.mean(), 1e-6)))
        m_w = np.zeros(d, dtype=np.float32)
        v_w = np.zeros(d, dtype=np.float32)
        m_b = v_b = 0.0
        step = 0
        for _ in range(epochs):
            order = rng.permutation(n)
            for s in range(0, n, batch):
                idx = order[s:s + batch]
                xb = Z[idx]
                yb = y[idx]
                p = 1.0 / (1.0 + np.exp(-(xb @ self.w + self.b)))
                err = (p - yb).astype(np.float32)
                gw = xb.T @ err / len(idx) + l2 * self.w
                gb = float(err.mean())
                step += 1
                m_w = 0.9 * m_w + 0.1 * gw
                v_w = 0.999 * v_w + 0.001 * gw * gw
                m_b = 0.9 * m_b + 0.1 * gb
                v_b = 0.999 * v_b + 0.001 * gb * gb
                mh = m_w / (1 - 0.9 ** step)
                vh = v_w / (1 - 0.999 ** step)
                self.w -= (lr * mh / (np.sqrt(vh) + 1e-8)).astype(np.float32)
                self.b -= lr * (m_b / (1 - 0.9 ** step)) / (
                    math.sqrt(v_b / (1 - 0.999 ** step)) + 1e-8)
        return self

    def predict_raw(self, X: np.ndarray) -> np.ndarray:
        Z = (X.astype(np.float32) - self.mu) / self.sd
        p = 1.0 / (1.0 + np.exp(-(Z @ self.w + self.b)))
        return p.astype(np.float64)

    def predict(self, X: np.ndarray) -> np.ndarray:
        p = self.predict_raw(X)
        if self.iso is not None:
            return np.interp(p, self.iso[0], self.iso[1])
        if self.calib is not None:
            return _apply_platt(p, *self.calib)
        return p


def _apply_platt(p: np.ndarray, a: float, b: float) -> np.ndarray:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    z = np.log(p / (1 - p))
    return 1.0 / (1.0 + np.exp(-(a * z + b)))


def _fit_platt(p: np.ndarray, y: np.ndarray) -> Optional[Tuple[float, float]]:
    """Platt scaling：把逻辑回归原始概率校准到验证集的实际频率。
    2 参数牛顿法，样本或正例过少时不校准。
    """
    y = np.asarray(y, dtype=np.float64)
    if len(y) < 200 or y.sum() < 30 or (1 - y).sum() < 30:
        return None
    p = np.clip(np.asarray(p, dtype=np.float64), 1e-6, 1 - 1e-6)
    z = np.log(p / (1 - p))
    a, b = 1.0, 0.0
    for _ in range(60):
        q = np.clip(1.0 / (1.0 + np.exp(-(a * z + b))), 1e-6, 1 - 1e-6)
        g_a = float(np.mean((q - y) * z))
        g_b = float(np.mean(q - y))
        w = q * (1 - q)
        h_aa = float(np.mean(w * z * z))
        h_ab = float(np.mean(w * z))
        h_bb = float(np.mean(w))
        det = h_aa * h_bb - h_ab * h_ab
        if abs(det) < 1e-12:
            break
        da = (h_bb * g_a - h_ab * g_b) / det
        db = (-h_ab * g_a + h_aa * g_b) / det
        a -= da
        b -= db
        if abs(da) + abs(db) < 1e-9:
            break
    a = float(min(max(a, 0.05), 3.0))
    b = float(min(max(b, -6.0), 6.0))
    return a, b


def _fit_isotonic(p: np.ndarray, y: np.ndarray,
                  n_bins: int = 50) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    """保序回归校准（PAVA）：直接学习“同分值区间的历史实际命中率”。
    比 Platt 更能修正高分尾部的高估。
    """
    p = np.asarray(p, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    if len(y) < 200 or y.sum() < 30:
        return None
    order = np.argsort(p, kind="mergesort")
    ps, ys = p[order], y[order]
    edges = np.linspace(0, len(ps), n_bins + 1).astype(int)
    xs, rate, wt = [], [], []
    for a, b in zip(edges[:-1], edges[1:]):
        if b - a < 30:
            continue
        xs.append(float(ps[a:b].mean()))
        rate.append(float(ys[a:b].mean()))
        wt.append(float(b - a))
    if len(xs) < 3:
        return None

    blocks = []
    for i, (r, w) in enumerate(zip(rate, wt)):
        blocks.append([r * w, w, i, i])
        while len(blocks) > 1 and (blocks[-2][0] / blocks[-2][1]
                                   > blocks[-1][0] / blocks[-1][1]):
            b2 = blocks.pop()
            b1 = blocks.pop()
            blocks.append([b1[0] + b2[0], b1[1] + b2[1], b1[2], b2[3]])

    vals = np.empty(len(xs), dtype=np.float64)
    for s, w, a, b in blocks:
        vals[a:b + 1] = s / w
    xs = np.asarray(xs)
    keep = np.concatenate([[True], np.diff(xs) > 1e-9])
    return xs[keep], vals[keep]


RANK_BUCKETS = [(1, 5), (6, 10), (11, 20), (21, 50), (51, 100),
                (101, 300), (301, 10 ** 9)]


def _rank_within_day(dates, p) -> pd.Series:
    s = pd.DataFrame({"date": dates, "p": p})
    return s.groupby("date")["p"].rank(ascending=False, method="first")


def _fit_rank_calib(dates, p, y) -> Optional[List[dict]]:
    """按同日排名分桶，统计各桶的实际晋级率（样本不足的桶跳过）。
    桶率用 PAVA 做单调化，避免名次越低概率反而越高的噪声。
    """
    if len(y) < 200 or float(np.sum(y)) < 20:
        return None
    rank = _rank_within_day(dates, p)
    tmp = pd.DataFrame({"rank": rank.values, "y": np.asarray(y, dtype=float)})
    raw = []
    for lo, hi in RANK_BUCKETS:
        m = (tmp["rank"] >= lo) & (tmp["rank"] <= hi)
        n = int(m.sum())
        if n >= 80:
            raw.append([lo, hi, n, float(tmp.loc[m, "y"].mean())])
    if not raw:
        return None
    # PAVA：随名次下降，命中率不得上升
    blocks = []
    for lo, hi, n, rate in raw:
        blocks.append([lo, hi, n, rate * n])
        while len(blocks) > 1 and (blocks[-2][3] / blocks[-2][2]
                                   < blocks[-1][3] / blocks[-1][2]):
            b2 = blocks.pop()
            b1 = blocks.pop()
            blocks.append([b1[0], b2[1], b1[2] + b2[2], b1[3] + b2[3]])
    return [{"lo": lo, "hi": hi, "n": n, "rate": s / n}
            for lo, hi, n, s in blocks]


def _apply_rank_calib(table: List[dict], dates, p) -> np.ndarray:
    rank = _rank_within_day(dates, p).values
    bounds = np.array([[b["lo"], b["hi"], b["rate"]] for b in table])
    idx = np.clip(np.searchsorted(bounds[:, 0], rank, side="right") - 1,
                  0, len(bounds) - 1)
    return bounds[idx, 2]


def _auc(y: np.ndarray, p: np.ndarray) -> float:
    pos = p[y == 1]
    neg = p[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    order = np.argsort(np.concatenate([pos, neg]))
    ranks = np.empty(len(order), dtype=np.float64)
    ranks[order] = np.arange(1, len(order) + 1)
    rp = ranks[:len(pos)].sum()
    return float((rp - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def _fit_predict(df: pd.DataFrame, label_col: str, train_mask: pd.Series,
                 target_mask: pd.Series, split_date: date):
    cols = FEATURES + ["date", "code", "name", "mv", "theme_name", label_col]
    tr = df.loc[train_mask, cols].replace([np.inf, -np.inf], np.nan)
    tr = tr.dropna(subset=FEATURES + [label_col])
    tr = tr[tr["date"] < split_date]
    va = df.loc[train_mask, cols].replace([np.inf, -np.inf], np.nan)
    va = va.dropna(subset=FEATURES + [label_col])
    va = va[va["date"] >= split_date]

    model = Logistic().fit(tr[FEATURES].values, tr[label_col].values.astype(np.float32))

    ev = {"n_train": int(len(tr)), "n_valid": int(len(va)),
          "base_rate": float(tr[label_col].mean() * 100)}
    if len(va) and va[label_col].nunique() > 1:
        pv_raw = model.predict(va[FEATURES].values)
        yv = va[label_col].values
        ev["auc"] = round(_auc(yv, pv_raw), 4)
        # 每日 Top-K 命中率（K=10/20）
        top = []
        for k in (10, 20):
            hits, days = 0, 0
            for _, day in va.assign(p=pv_raw).groupby("date"):
                if len(day) < k:
                    continue
                hits += int(day.nlargest(k, "p")[label_col].sum())
                days += 1
            top.append({"k": k, "hit_rate": round(hits / (days * k) * 100, 2)
                        if days else None, "days": days})
        ev["topk"] = top
        # 概率校准：按“同一交易日内的候选排名”分桶，直接取该桶的历史晋级率。
        # 输出是按排名展示的榜单，这种口径比全局 isotonic 更贴合实际读法
        # （isotonic 的高分桶会混入大量低分票，导致顶部概率被稀释）。
        model.rank_table = _fit_rank_calib(va["date"].values, pv_raw, yv)
        if model.rank_table:
            pv = _apply_rank_calib(model.rank_table, va["date"].values, pv_raw)
            ev["calibration_method"] = "rank"
        else:
            model.iso = _fit_isotonic(pv_raw, yv)
            if model.iso is None:
                model.calib = _fit_platt(pv_raw, yv)
            pv = model.predict(va[FEATURES].values)
            ev["calibration_method"] = ("isotonic" if model.iso is not None
                                        else "platt" if model.calib else "none")
        # 校准后分档核对
        bins = [0, 0.02, 0.05, 0.10, 0.20, 1.0]
        calib = []
        for lo, hi in zip(bins[:-1], bins[1:]):
            m = (pv >= lo) & (pv < hi)
            if m.sum() < 20:
                continue
            calib.append({"bin": f"{lo*100:.0f}-{hi*100:.0f}%",
                          "n": int(m.sum()),
                          "pred": round(float(pv[m].mean() * 100), 2),
                          "actual": round(float(yv[m].mean() * 100), 2)})
        ev["calibration"] = calib
        if model.rank_table:
            ev["rank_calibration"] = [
                {"rank": f"{b['lo']}-{'∞' if b['hi'] >= 10**8 else b['hi']}",
                 "n": b["n"], "rate": round(b["rate"] * 100, 1)}
                for b in model.rank_table]

    # 目标日预测（不需要 T+1 数据）
    tgt = df.loc[target_mask, cols].replace([np.inf, -np.inf], np.nan)
    tgt = tgt.dropna(subset=FEATURES)
    if len(tgt):
        tgt = tgt.copy()
        tgt["score_raw"] = model.predict_raw(tgt[FEATURES].values)
        if model.rank_table:
            tgt["prob"] = _apply_rank_calib(
                model.rank_table, tgt["date"].values, tgt["score_raw"].values)
        else:
            tgt["prob"] = model.predict(tgt[FEATURES].values)
    return model, ev, tgt


# ─────────────────────────── 主流程 ───────────────────────────

def _phase(zt_today: int, zt3: List[int], height: int,
          broken: int = 0, broken_prev: int = 0, high_broken: bool = False) -> str:
    """高度够 3 板不够把题材叫成启动期。涨停掉下来、高位断板或炸板变多，先是分歧。"""
    if zt_today <= 0:
        return "无涨停"
    seq = list(zt3[-3:])
    prev = seq[-2] if len(seq) >= 2 else None
    rising = prev is not None and zt_today > prev
    falling = prev is not None and zt_today < prev and (prev - zt_today) >= max(3, int(prev * 0.2))
    broken_up = broken > broken_prev and broken >= 3
    if prev is not None and prev >= 8 and zt_today * 2 <= prev:
        return "退潮 / 冰点"
    if falling and (high_broken or broken_up or height >= 3):
        return "分歧期"
    if broken_up and not rising:
        return "分歧期"
    if height >= 6 and not falling:
        return "高潮期"
    if height >= 4 and (rising or prev is None):
        return "发酵期"
    if height >= 3 and rising:
        return "启动期"
    if rising or (prev is None and zt_today > 0 and height < 3):
        return "聚集未完成"
    if falling:
        return "分歧期"
    return "分歧期"


def _fmt_reason(row) -> List[str]:
    r = []
    c60 = row.get("cum60")
    if pd.notna(c60):
        if c60 < -30:
            r.append(f"深跌{abs(c60):.0f}%(60日)")
        elif c60 < -15:
            r.append(f"低位({c60:.0f}%/60日)")
        elif c60 < 0:
            r.append(f"中低位({c60:.0f}%)")
        elif c60 > 15:
            r.append(f"强势(+{c60:.0f}%/60日)")
    vr = row.get("vol_ratio5")
    if pd.notna(vr):
        if vr >= 2:
            r.append(f"放量{vr:.1f}倍")
        elif vr >= 1.2:
            r.append(f"温和放量{vr:.1f}倍")
        elif vr <= 0.8:
            r.append(f"缩量{vr:.1f}倍")
    if row.get("is_sealed"):
        r.append("收在最高")
    elif pd.notna(row.get("upper_shadow")) and row["upper_shadow"] > 2:
        r.append(f"上影{row['upper_shadow']:.1f}%")
    tz = row.get("theme_zt")
    if pd.notna(tz) and tz > 0:
        r.append(f"题材今日{int(tz)}只涨停")
    kind = row.get("pattern_kind")
    if isinstance(kind, str) and kind:
        r.insert(0, kind)
    return r


def predict(conn, target_date: Optional[date] = None,
            top_first: int = 15, top_second: int = 10) -> dict:
    if target_date is None:
        target_date = _query(conn, "SELECT max(date) d FROM stock_daily").iloc[0, 0]
        if isinstance(target_date, datetime):
            target_date = target_date.date()

    start = (target_date - timedelta(days=460)).isoformat()
    df = load_history(conn, start)
    if df.empty:
        raise RuntimeError("stock_daily 无数据")
    idx = load_index(conn, start)
    themes = load_themes(conn)
    df = build_features(df, idx, themes)

    # 训练/验证切分：最后 35 个交易日做验证
    dates = sorted(df["date"].unique())
    split_date = dates[-35] if len(dates) > 60 else dates[int(len(dates) * 0.85)]
    max_mv = 300.0

    date_ok = df["date"] == target_date
    name_ok = ~df["name"].fillna("").str.contains("ST|退", regex=True)
    eligible = (
        (df["mv"] < max_mv) & (df["volume"].fillna(0) > 0)
        & (~df["is_st"].fillna(False)) & (~df["is_suspended"].fillna(False))
        & name_ok
        & (df["is_lu"] | df["cum60"].notna())
    )
    m1_train = eligible & df["next_ok"].fillna(False) & (~df["is_lu"])
    m2_train = eligible & df["next_ok"].fillna(False) & df["is_first"]
    m1_target = eligible & (~df["is_lu"]) & (df["date"] == target_date)
    m2_target = eligible & df["is_first"] & (df["date"] == target_date)

    model1, ev1, tgt1 = _fit_predict(df, "next_lu", m1_train, m1_target, split_date)
    model2, ev2, tgt2 = _fit_predict(df, "next_lu", m2_train, m2_target, split_date)

    zt_today = load_zt_today(conn, target_date)
    zb_today = load_zb_today(conn, target_date)
    dt_today = load_dt_today(conn, target_date)
    fund = load_fund_today(conn, target_date)
    fund_map = {r["code"]: r for _, r in fund.iterrows()} if len(fund) else {}
    zt_map = {r["code"]: r for _, r in zt_today.iterrows()} if len(zt_today) else {}
    zb_map = {r["code"]: r for _, r in zb_today.iterrows()} if len(zb_today) else {}

    prev = dates[dates.index(target_date) - 1] if target_date in dates and dates.index(target_date) else None
    zb_prev = load_zb_today(conn, prev) if prev else zb_today.iloc[0:0]
    mem = themes_on(themes, target_date)
    stats = _sector_stats(df, mem, target_date, prev, zb_today, zb_prev)
    hot_parents = {sec: node["name"] for sec, node in stats.items() if node.get("zt", 0) >= 3}
    tree = load_plate_tree(hot_parents)
    labels = _labels_for(mem, stats, tree)

    tgt1 = _screen(tgt1, df, labels, "first")
    tgt2 = _screen(tgt2, df, labels, "second")
    first = _pack(tgt1, top_first, zt_map, zb_map, fund_map, labels, "first")
    second = _pack(tgt2, top_second, zt_map, zb_map, fund_map, labels, "second")

    # 按题材归组；“无题材归属”永远放最后
    def group(items):
        g: Dict[str, dict] = {}
        for it in items:
            name = it["theme"] or "无题材归属"
            node = g.setdefault(name, {"theme": name, "zt_today": it["theme_zt_today"],
                                       "zt3": it["theme_zt3"], "height": it["theme_height"],
                                       "phase": it["phase"], "candidates": []})
            node["candidates"].append(it)
        return sorted(g.values(), key=lambda x: (x["theme"] == "无题材归属",
                                                 -max(c["prob"] for c in x["candidates"]),
                                                 -x["zt_today"]))

    market = _market_snapshot(df, target_date, zt_today, zb_today, dt_today)
    next_td = _next_trade_date(conn, target_date)
    strict = df.loc[df["date"] == target_date].set_index("code")["board_days"]

    highs = []
    for _, r in zt_today.iterrows():
        b = int(strict.get(r["code"], 0) or 0)
        if b < 3:
            continue
        lab = labels.get(r["code"]) or {}
        highs.append({"code": r["code"], "name": r["name"],
                      "board_days": b,
                      "pct": float(r["pct"] or 0),
                      "theme": lab.get("theme") or ""})
    highs.sort(key=lambda x: -x["board_days"])

    panic = _panic_watch(df, target_date, max_mv)
    gaps = _data_gaps(df, zt_today, target_date, themes, fund)
    auc2 = (ev2 or {}).get("auc")
    if auc2 is not None and auc2 < 0.65:
        gaps.append(
            f"二板模型 AUC {auc2}，排序仍然弱于首板。名单已按形态和风口过滤，不按老龙反包来排"
        )
    watchlist = _watchlist(mem, stats, tree, df, zt_today, target_date, first, second)

    return {
        "as_of": str(target_date),
        "next_trade_date": str(next_td) if next_td else None,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "market": market,
        "model": {"first": ev1, "second": ev2},
        "first_board": {
            "groups": group(first),
            "n_candidates": len(tgt1),
        },
        "second_board": {
            "groups": group(second),
            "n_candidates": len(tgt2),
        },
        "risk": {
            "high_board": highs[:8],
            "chase_warning": _chase_warning(market, second),
            "panic_watch": panic,
        },
        "gaps": gaps,
        "watchlist": watchlist,
    }


def _labels_for(mem: pd.DataFrame, stats: dict, tree: dict) -> dict:
    labels = {}
    if mem.empty:
        return labels
    for code, g in mem.groupby("code"):
        labels[code] = _pick_theme(g, stats, tree)
    return labels


def _screen(tgt: pd.DataFrame, df: pd.DataFrame, labels: dict, kind: str) -> pd.DataFrame:
    if tgt is None or len(tgt) == 0:
        return tgt
    flags = df.loc[tgt.index, ["pattern_ok", "old_dragon", "pattern_kind"]]
    out = tgt.copy()
    out["pattern_ok"] = flags["pattern_ok"].to_numpy()
    out["old_dragon"] = flags["old_dragon"].to_numpy()
    out["pattern_kind"] = flags["pattern_kind"].to_numpy()
    if kind == "first":
        out = out[out["pattern_ok"].fillna(False)]
    else:
        out = out[~out["old_dragon"].fillna(False)]
    keep = []
    for idx, r in out.iterrows():
        lab = labels.get(r["code"]) or {}
        if lab.get("phase") in HOT_PHASES:
            keep.append(idx)
    return out.loc[keep]


def _watchlist(mem, stats, tree, df, zt_today, d, first, second) -> List[dict]:
    """每个风口题材：要看的个股、可能的一板、可能的二板。"""
    strict = df.loc[df["date"] == d].set_index("code")["board_days"]
    buckets: Dict[str, dict] = {}

    def node(theme, phase):
        return buckets.setdefault(theme, {
            "theme": theme, "phase": phase, "leaders": [], "first": [], "second": [],
        })

    if len(zt_today):
        for _, r in zt_today.iterrows():
            sub = mem[mem["code"] == r["code"]] if len(mem) else mem
            lab = _pick_theme(sub, stats, tree)
            if not lab.get("theme"):
                continue
            if lab.get("phase") not in HOT_PHASES and int(lab.get("zt") or 0) < 5:
                continue
            b = int(strict.get(r["code"], 0) or 0)
            node(lab["theme"], lab["phase"])["leaders"].append({
                "code": r["code"], "name": r["name"], "board": b,
            })
    for kind, items in (("first", first), ("second", second)):
        for it in items:
            if not it.get("theme"):
                continue
            node(it["theme"], it.get("phase") or "")[kind].append({
                "code": it["code"], "name": it["name"], "prob": it["prob"],
            })
    out = []
    for g in buckets.values():
        g["leaders"] = sorted(g["leaders"], key=lambda x: -x["board"])[:6]
        if not g["leaders"] and not g["first"] and not g["second"]:
            continue
        out.append(g)
    out.sort(key=lambda g: (-(g["leaders"][0]["board"] if g["leaders"] else 0), g["theme"]))
    return out[:24]


def _pack(tgt: pd.DataFrame, top: int, zt_map, zb_map, fund_map,
          labels, kind: str) -> List[dict]:
    if tgt is None or len(tgt) == 0:
        return []
    sort_col = "score_raw" if "score_raw" in tgt.columns else "prob"
    tgt = tgt.sort_values(sort_col, ascending=False).head(top)
    out = []
    for _, r in tgt.iterrows():
        code = r["code"]
        z = zt_map.get(code)
        zb = zb_map.get(code)
        f = fund_map.get(code)
        lab = labels.get(code) or {}
        theme = lab.get("theme") or ""
        reasons = _fmt_reason(r)
        if z is not None:
            if z["first_seal_time"]:
                reasons.append(f"首封{str(z['first_seal_time'])[:5]}")
            if z["seal_amount"]:
                reasons.append(f"封单{float(z['seal_amount']) / 1e4:.0f}万")
            reason_text = str(z["reason"] or z["theme"] or "").strip()
            if reason_text:
                reasons.append(f"涨停原因:{reason_text[:24]}")
        if zb is not None and int(zb["break_times"] or 0) > 0:
            reasons.append(f"今日炸板{int(zb['break_times'])}次")
        if f is not None and pd.notna(f["main_net_pct"]):
            reasons.append(f"主力净占比{float(f['main_net_pct']):+.1f}%")
        out.append({
            "code": code,
            "name": r.get("name", ""),
            "prob": round(float(r["prob"]) * 100, 1),
            "theme": theme,
            "theme_role": lab.get("role") or "",
            "theme_zt_today": int(lab.get("zt") or 0),
            "theme_zt3": lab.get("zt3") or [],
            "theme_height": int(lab.get("height") or 0),
            "phase": lab.get("phase") or "无涨停",
            "reasons": reasons,
            "board_condition": ("明日涨停即二板" if kind == "second"
                                else "明日涨停即首板"),
            "circ_mv": round(float(r["mv"]), 1) if pd.notna(r.get("mv")) else None,
            "cum60": round(float(r["cum60"]), 1) if pd.notna(r.get("cum60")) else None,
        })
    return out


def _theme_series(df: pd.DataFrame, themes: pd.DataFrame) -> Dict[str, List[int]]:
    if themes.empty:
        return {}
    dates = sorted(df["date"].unique())[-8:]
    lu = df.loc[df["is_lu"] & df["date"].isin(dates), ["date", "code"]]
    td = lu.merge(themes.drop_duplicates(["code", "sector_code"]),
                  on="code", how="inner")
    cnt = td.groupby(["date", "sector_code"]).size()
    out: Dict[str, List[int]] = {}
    name_of = themes.drop_duplicates("sector_code").set_index("sector_code")["sector_name"]
    for sc in themes["sector_code"].unique():
        nm = name_of.get(sc)
        if nm in out:
            continue
        out[nm] = [int(cnt.get((d, sc), 0)) for d in dates[-3:]]
    return out


def _next_trade_date(conn, d: date) -> Optional[date]:
    df = _query(conn, """
        SELECT cal_date FROM trade_cal
        WHERE market = 'SSE' AND cal_date > %s AND is_open = 1
        ORDER BY cal_date LIMIT 1
    """, [d])
    if df.empty:
        return None
    v = df.iloc[0, 0]
    return v.date() if isinstance(v, datetime) else v


def _market_snapshot(df, d, zt_today, zb_today, dt_today=None) -> dict:
    day = df[df["date"] == d]
    lu = int(len(zt_today)) if zt_today is not None and len(zt_today) else int(day["is_lu"].sum())
    ld = int(len(dt_today)) if dt_today is not None and len(dt_today) else int(day["is_ld"].sum())
    up = int((day["pct"] > 0).sum())
    down = int((day["pct"] < 0).sum())
    height = int(day["board_days"].max()) if len(day) else 0
    seal = int(len(zt_today))
    broken = int(len(zb_today))
    seal_rate = round(seal / max(seal + broken, 1) * 100, 1)
    if lu < 30:
        bucket = "冰点<30"
    elif lu < 60:
        bucket = "30-60"
    elif lu < 100:
        bucket = "60-100"
    else:
        bucket = "火热>100"
    # 今日首板数 & 昨日首板今日晋级率（连板温度）
    first_today = int(day["is_first"].sum())
    dates = sorted(df["date"].unique())
    promote, n_prev_first = None, 0
    if d in dates and dates.index(d) > 0:
        prev = dates[dates.index(d) - 1]
        pf = df[(df["date"] == prev) & df["is_first"] & df["next_ok"].fillna(False)]
        n_prev_first = int(len(pf))
        if n_prev_first:
            promote = round(float(pf["next_lu"].mean() * 100), 1)
    idx_pct = float(day["idx_pct"].dropna().iloc[0]) if day["idx_pct"].notna().any() else None
    n_elig = int(((day["mv"] < 300) & day["volume"].fillna(0) > 0).sum())
    return {
        "limit_up": lu, "limit_down": ld, "up": up, "down": down,
        "max_board": height, "seal_rate": seal_rate,
        "broken": broken, "sentiment": bucket,
        "first_board_today": first_today,
        "yesterday_first_promote": promote,
        "yesterday_first_n": n_prev_first,
        "index_pct": round(idx_pct, 2) if idx_pct is not None else None,
        "eligible_stocks": n_elig,
        "base_first_board_pct": round(lu / max(n_elig, 1) * 100, 1),
    }


def _chase_warning(market, second) -> str:
    if market["sentiment"] in ("60-100", "火热>100"):
        return ("情绪偏热：明日高开是兑现点，开盘追高的历史期望为负"
                "（F-024）；等回踩看承接，不在集合竞价/开盘直接追。")
    if market["sentiment"] == "冰点<30":
        return ("情绪冰点：涨停股是资金抱团结果，首板/二板延续率反而较高；"
                "但冰点样本少，仓位上仍按试错处理。")
    return "情绪中性：按个股与题材条件执行，不因指数涨跌改变追高纪律（F-024）。"


def _panic_watch(df, d, max_mv) -> List[dict]:
    day = df[(df["date"] == d) & (df["mv"] < max_mv)
             & (~df["is_st"].fillna(False))].dropna(subset=["cum3", "vol_ratio5"])
    day = day[~day["name"].fillna("").str.contains("ST|退", regex=True)]
    sig = day[(day["cum3"] <= -8) & (day["cum3"] >= -35) & (day["vol_ratio5"] >= 1.2)]
    sig = sig.sort_values("cum3").head(8)
    out = []
    for _, r in sig.iterrows():
        out.append({
            "code": r["code"], "name": r["name"],
            "cum3": round(float(r["cum3"]), 1),
            "vol_ratio5": round(float(r["vol_ratio5"]), 1),
            "close_pos": round(float(r["close_pos"]), 2),
            "note": ("收在最低20%：真恐慌，明日若继续放量杀跌是T+1/T+2反手观察点"
                     if r["close_pos"] <= 0.2 else
                     "盘中已拉回：反手买可能已发生，次日不追（F-026）"),
        })
    return out


def _data_gaps(df, zt_today, d, themes, fund) -> List[str]:
    gaps = []
    if len(zt_today) == 0:
        gaps.append(f"zt_pool 在 {d} 无数据")
    if df.loc[df["date"] == d, "amount"].isna().all():
        gaps.append("stock_daily.amount 历史缺失，成交额未参与模型")
    if not themes.empty:
        start = themes["effective_from"].min()
        gaps.append(
            f"{start} 之前没有开盘啦归属，那些日子题材特征记 0，不用后来才出现的映射"
        )
    gaps.append(
        "2026-10-08 之前没有逐日流通市值，那些日子用该股第一次观测到的流通市值，不用之后更新的值"
    )
    gaps.append("北向买卖额交易所已停更，库里没有公开序列，没有用别的数代替")
    gaps.append("没有讨论区原文。人气用 theme_heat 里的同花顺热股和热概念，不另编热度")
    if fund is not None and len(fund) < 1000:
        gaps.append(f"{d} fund_flow_stock 只有 {len(fund)} 条，个股资金流不完整")
    if len(df[df["date"] == d]) < 3000:
        gaps.append(f"{d} 日线覆盖不足（{len(df[df['date']==d])} 只）")
    return gaps


# ─────────────────────────── Markdown ───────────────────────────

def render_markdown(r: dict) -> str:
    m = r["market"]
    nxt = r.get("next_trade_date") or "下一交易日"
    lines = []
    lines.append(f"## 明日首板/二板预测（基准日 {r['as_of']} 收盘 → {nxt}）\n")
    lines.append(
        f"**情绪底座**：涨停 **{m['limit_up']}** / 跌停 **{m['limit_down']}** / "
        f"最高 **{m['max_board']}** 板 / 封板率 **{m['seal_rate']}%** / "
        f"情绪档 **{m['sentiment']}**"
        + (f" / 上证 {m['index_pct']:+.2f}%" if m["index_pct"] is not None else "")
    )
    extra = f"**今日首板 {m['first_board_today']} 只**"
    if m.get("yesterday_first_promote") is not None:
        extra += (f" / 昨日首板今日晋级率 **{m['yesterday_first_promote']}%**"
                  f"（{m['yesterday_first_n']} 进 {round(m['yesterday_first_promote'] * m['yesterday_first_n'] / 100)}）")
    lines.append(f"\n{extra}")
    lines.append(f"\n基准：全市场个股明日涨停率约 **{m['base_first_board_pct']}%**；"
                 f"今日首板明日晋级二板的历史基准约 **{r['model']['second']['base_rate']:.1f}%**。"
                 f"概率 = 同一交易日候选排名对应的历史晋级率（近 35 个交易日回算）。\n")

    for key, title, note in (
        ("second_board", "二板候选（今日首板 → 明日二板）",
         "二板是“题材发酵确认”，概率来自首板同日条件；开盘一致性兑现，别在跳空上追。"),
        ("first_board", "首板候选（今日未涨停 → 明日首板）",
         "只留前期缩量后连续放量，或急跌之后放量上影还在放大，并且落在风口题材上的票。过往龙头、反包不进这个名单。"),
    ):
        lines.append(f"\n### {title}\n")
        lines.append(f"_{note}_\n")
        groups = r[key]["groups"]
        if not groups:
            lines.append("无合格候选。\n")
            continue
        for g in groups:
            seq = "→".join(str(x) for x in g["zt3"]) if g["zt3"] else "-"
            lines.append(f"\n**{g['theme']}** ｜ 今日涨停 {g['zt_today']} 只（近3日 {seq}）"
                         f"｜ 最高 {g['height']} 板 ｜ {g['phase']}\n")
            for c in g["candidates"]:
                reason = "；".join(c["reasons"]) if c["reasons"] else "无显著特征"
                lines.append(
                    f"- **{c['name']}（{c['code']}）** 概率 **{c['prob']}%** ｜ "
                    f"{c['board_condition']} ｜ {reason}")
            lines.append("")

    risk = r["risk"]
    lines.append("\n### 明日风险与观察\n")
    lines.append(f"- **追高纪律**：{risk['chase_warning']}")
    if risk["high_board"]:
        hb = "、".join(f"{x['name']}({x['board_days']}板)" for x in risk["high_board"][:6])
        lines.append(f"- **高位断板观察**：{hb}——断板是题材退潮的第一信号，别用仓位去赌晋级。")
    if risk["panic_watch"]:
        p = "、".join(f"{x['name']}({x['cum3']:.1f}%)" for x in risk["panic_watch"][:5])
        lines.append(f"- **恐慌反手观察**：{p}——只有“放量+收在最低”才是买点；"
                     f"周五恐慌的买点在周一杀跌之后（F-025/F-026）。")
    else:
        lines.append("- **恐慌反手观察**：今日无 3 日跌≥8%+放量的标的，不需要准备反手买。")

    lines.append("\n### 模型可信度与缺口\n")
    for k, label in (("first", "首板"), ("second", "二板")):
        e = r["model"][k]
        extra = f"，AUC {e['auc']}" if "auc" in e else ""
        top = next((x for x in e.get("topk", []) if x["k"] == 10), None) if e.get("topk") else None
        t = f"，每日Top10命中率 {top['hit_rate']}%" if top and top.get("hit_rate") is not None else ""
        lines.append(f"- {label}模型：训练 {e['n_train']} 条 / 验证 {e['n_valid']} 条，"
                     f"基准 {e['base_rate']:.1f}%{extra}{t}")
        cal = e.get("calibration") or []
        if cal:
            top_bin = cal[-1]
            lines.append(f"  - 校准核对（最高档 {top_bin['bin']}）：预测均值 "
                         f"{top_bin['pred']}% vs 实际 {top_bin['actual']}%（n={top_bin['n']}）")
        rc = e.get("rank_calibration") or []
        if rc:
            tbl = " / ".join(f"{x['rank']}名 {x['rate']}%" for x in rc[:5])
            lines.append(f"  - 排名命中率：{tbl}")
    for g in r["gaps"]:
        lines.append(f"- 缺口：{g}")
    lines.append("\n_概率是历史条件频率的估计，不是承诺；不构成投资建议，不荐股。_")
    return "\n".join(lines)
