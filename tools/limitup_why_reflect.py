#!/usr/bin/env python3
"""当日涨停反思：先出证据，再把 yan 的总结写入迭代认知。

pack  只读。列出当天全部涨停，以及已经在库里的迭代认知标题。
commit 读 yan 写好的 JSON，按标题并入 H- 迭代认知。状态保持 candidate。
       不写基础认知，不升 active，不荐股。

commit 的 JSON：
{
  "as_of": "YYYY-MM-DD",
  "items": [
    {
      "title": "同一原因以后用同一标题",
      "statement": "一句可检验的话",
      "why": "这批今天为什么能涨停",
      "codes": ["sz000001"],
      "themes": ["题材名"],
      "derives_from": ["F-011"],
      "falsify": "什么情况下这条不成立"
    }
  ]
}
当天涨停池里的代码必须全部出现，且每只只出现一次。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import psycopg2
import yaml

SECRETS = Path(__file__).resolve().parent.parent / "configs" / "secrets.yaml"
BANNED = ("买入", "卖出", "目标价", "必涨", "荐股", "加仓", "满仓")


def _conn(role="reader"):
    sec = yaml.safe_load(SECRETS.read_text())["database"]
    if role == "d12":
        user, key = "duser_d12writer", "duser_d12writer_password"
    else:
        user, key = "duser_reader", "duser_reader_password"
    return psycopg2.connect(
        host="127.0.0.1", port=15432, dbname="market_tsdb",
        user=user, password=sec[key],
    )


def _day(cur, day: str | None) -> str:
    if day:
        return day
    cur.execute("SELECT max(date)::text FROM zt_pool")
    row = cur.fetchone()
    if not row or not row[0]:
        raise SystemExit("涨停池是空的")
    return row[0]


def _existing(cur) -> list[dict]:
    cur.execute(
        """
        SELECT DISTINCT ON (cognition_id)
               cognition_id, version, title, statement, status,
               validations, derives_from
        FROM cognition
        WHERE type = 'iterative'
        ORDER BY cognition_id, version DESC
        """
    )
    out = []
    for cid, ver, title, statement, status, validations, derives in cur.fetchall():
        vals = validations if isinstance(validations, list) else []
        dates = [v.get("date") for v in vals if isinstance(v, dict)]
        out.append({
            "cognition_id": cid,
            "version": ver,
            "title": title,
            "statement": statement,
            "status": status,
            "dates": dates,
            "derives_from": derives or [],
        })
    return out


def _volume_shift(bars: list[tuple]) -> dict | None:
    """近 10 个交易日里，第一次成交量达到前 5 日均量 1.5 倍的日子。只标位置，不当成已经确认的进场。"""
    if len(bars) < 6:
        return None
    start = max(5, len(bars) - 10)
    for i in range(start, len(bars)):
        prev = [b["volume"] for b in bars[i - 5:i] if b["volume"]]
        vol = bars[i]["volume"]
        if len(prev) < 5 or not vol:
            continue
        ratio = vol / (sum(prev) / len(prev))
        if ratio >= 1.5:
            return {"date": bars[i]["date"], "vol_ratio": round(ratio, 2)}
    return None


def _intraday(rows: list[tuple]) -> dict | None:
    """rows: (hhmm, vol, amount, price, avg) 按时间升序。"""
    if not rows:
        return None
    amounts = [a or 0 for _t, _v, a, _p, _g in rows]
    vols = [v or 0 for _t, v, _a, _p, _g in rows]
    day_amount = sum(amounts)
    median_vol = sorted(vols)[len(vols) // 2] or 1
    top = []
    for i in sorted(range(len(rows)), key=lambda k: amounts[k], reverse=True)[:3]:
        hhmm, vol, amount, price, avg = rows[i]
        nxt = rows[i + 5][3] if i + 5 < len(rows) else None
        share = (amount / day_amount * 100) if day_amount and amount else None
        vs_avg = (price / avg - 1) * 100 if price and avg else None
        next_pct = (nxt / price - 1) * 100 if nxt and price else None
        top.append({
            "time": hhmm,
            "amount_share_pct": None if share is None else round(share, 1),
            "vol_vs_median": round((vol or 0) / median_vol, 2),
            "price": price,
            "vs_avg_pct": None if vs_avg is None else round(vs_avg, 2),
            "next_5bars_pct": None if next_pct is None else round(next_pct, 2),
        })
    return {"top_amount_minutes": top}


def _strict_and_path(bars: list[dict]) -> tuple[int, str]:
    """bars ascending, last row is the limit-up day."""
    if not bars:
        return 0, "首板"
    height = 0
    for bar in reversed(bars):
        pct = bar["pct"]
        if pct is not None and pct >= 9.8:
            height += 1
        else:
            break
    prior = bars[:-1]
    if height >= 2:
        return height, "连板"
    if len(prior) >= 3:
        last3 = prior[-3:]
        if all(b["pct"] is not None and b["pct"] < 0 for b in last3):
            cum3 = sum(b["pct"] for b in last3)
            window = prior[-20:]
            hi = max((b["high"] for b in window if b["high"]), default=None)
            close = last3[-1]["close"]
            dist = (close / hi - 1) * 100 if hi and close else 0
            if cum3 <= -8 and dist <= -15:
                return height, "此前连续下跌跌出空间"
    return height, "首板"


def pack(day: str | None) -> dict:
    conn = _conn()
    cur = conn.cursor()
    day = _day(cur, day)
    cur.execute(
        """
        SELECT z.code, coalesce(z.name, ''), z.reason, z.theme, z.board_days,
               z.first_seal_time::text, z.break_times, z.pct, d.circ_mv
        FROM zt_pool z
        LEFT JOIN stock_daily d ON d.code = z.code AND d.date = z.date
        WHERE z.date = %s
        ORDER BY z.code
        """,
        (day,),
    )
    zt = cur.fetchall()
    codes = [r[0] for r in zt]
    themes: dict[str, list[str]] = {c: [] for c in codes}
    bars: dict[str, list] = {c: [] for c in codes}
    minutes: dict[str, list] = {c: [] for c in codes}
    if codes:
        cur.execute(
            """
            SELECT code, sector_name
            FROM stock_sector_map
            WHERE kind = 'theme' AND sector_code ~ '^801'
              AND code = ANY(%s)
              AND effective_from <= %s
              AND (effective_to IS NULL OR effective_to > %s)
            ORDER BY code, sector_name
            """,
            (codes, day, day),
        )
        for code, name in cur.fetchall():
            themes.setdefault(code, []).append(name)
        cur.execute(
            """
            SELECT code, date::text, pct, open, high, low, close, volume
            FROM stock_daily
            WHERE code = ANY(%s)
              AND date <= %s
              AND date >= %s::date - 40
            ORDER BY code, date
            """,
            (codes, day, day),
        )
        for code, d, pct, open_, high, low, close, volume in cur.fetchall():
            bars.setdefault(code, []).append({
                "date": d, "pct": pct, "open": open_, "high": high,
                "low": low, "close": close, "volume": volume,
            })
        cur.execute(
            """
            SELECT code,
                   to_char(ts AT TIME ZONE 'Asia/Shanghai', 'HH24:MI'),
                   vol, amount, price, avg_price
            FROM stock_minute
            WHERE code = ANY(%s) AND freq = '1m'
              AND ts >= %s::date AND ts < %s::date + 1
            ORDER BY code, ts
            """,
            (codes, day, day),
        )
        for code, hhmm, vol, amount, price, avg in cur.fetchall():
            minutes.setdefault(code, []).append((hhmm, vol, amount, price, avg))
    stocks = []
    for code, name, reason, ths_theme, board_days, first_seal, breaks, pct, circ in zt:
        series = bars.get(code, [])
        height, path = _strict_and_path(series)
        recent = []
        for i, bar in enumerate(series[-6:]):
            idx = len(series) - len(series[-6:]) + i
            prev = [b["volume"] for b in series[max(0, idx - 5):idx] if b["volume"]]
            ratio = None
            if prev and bar["volume"]:
                ratio = round(bar["volume"] / (sum(prev) / len(prev)), 2)
            recent.append({
                "date": bar["date"],
                "pct": None if bar["pct"] is None else round(float(bar["pct"]), 2),
                "vol_ratio": ratio,
            })
        today = series[-1] if series and series[-1]["date"] == day else None
        day_shape = None
        if today and today["high"] and today["low"] and today["close"]:
            span = today["high"] - today["low"]
            close_pos = (today["close"] - today["low"]) / span if span else 1.0
            shadow = (today["high"] - today["close"]) / today["close"] * 100
            day_shape = {
                "open": today["open"],
                "high": today["high"],
                "low": today["low"],
                "close": today["close"],
                "close_pos": round(close_pos, 2),
                "upper_shadow_pct": round(shadow, 2),
                "vol_ratio5": recent[-1]["vol_ratio"] if recent else None,
            }
        intra = _intraday(minutes.get(code, []))
        stocks.append({
            "code": code,
            "name": name,
            "pct": None if pct is None else round(float(pct), 2),
            "circ_mv_yi": None if circ is None else round(float(circ), 2),
            "ths_reason": reason or "",
            "ths_theme": ths_theme or "",
            "board_days_cumulative": board_days,
            "strict_board": height,
            "path": path,
            "first_seal_time": first_seal,
            "break_times": breaks,
            "themes": themes.get(code, []),
            "recent": recent,
            "volume_shift": _volume_shift(series),
            "day": day_shape,
            "intraday": intra,
        })
    cur.execute(
        """
        SELECT z.code, coalesce(z.name, ''), z.industry, z.pct, z.first_seal_time::text,
               z.break_times, z.board_days, d.circ_mv
        FROM dt_pool z
        LEFT JOIN stock_daily d ON d.code = z.code AND d.date = z.date
        WHERE z.date = %s
        ORDER BY z.code
        """,
        (day,),
    )
    dt_rows = cur.fetchall()
    dt_codes = [r[0] for r in dt_rows]
    dt_bars: dict[str, list] = {c: [] for c in dt_codes}
    dt_minutes: dict[str, list] = {c: [] for c in dt_codes}
    dt_themes: dict[str, list] = {c: [] for c in dt_codes}
    prior_lu: dict[str, list] = {c: [] for c in dt_codes}
    if dt_codes:
        cur.execute(
            """
            SELECT code, sector_name FROM stock_sector_map
            WHERE kind = 'theme' AND sector_code ~ '^801' AND code = ANY(%s)
              AND effective_from <= %s AND (effective_to IS NULL OR effective_to > %s)
            ORDER BY code, sector_name
            """,
            (dt_codes, day, day),
        )
        for code, name in cur.fetchall():
            dt_themes.setdefault(code, []).append(name)
        cur.execute(
            """
            SELECT code, date::text, pct, open, high, low, close, volume
            FROM stock_daily
            WHERE code = ANY(%s) AND date <= %s AND date >= %s::date - 40
            ORDER BY code, date
            """,
            (dt_codes, day, day),
        )
        for code, d, pct, open_, high, low, close, volume in cur.fetchall():
            dt_bars.setdefault(code, []).append({
                "date": d, "pct": pct, "open": open_, "high": high,
                "low": low, "close": close, "volume": volume,
            })
        cur.execute(
            """
            SELECT code, to_char(ts AT TIME ZONE 'Asia/Shanghai', 'HH24:MI'),
                   vol, amount, price, avg_price
            FROM stock_minute
            WHERE code = ANY(%s) AND freq = '1m'
              AND ts >= %s::date AND ts < %s::date + 1
            ORDER BY code, ts
            """,
            (dt_codes, day, day),
        )
        for code, hhmm, vol, amount, price, avg in cur.fetchall():
            dt_minutes.setdefault(code, []).append((hhmm, vol, amount, price, avg))
        cur.execute(
            """
            SELECT code, date::text FROM zt_pool
            WHERE code = ANY(%s) AND date < %s AND date >= %s::date - 20
            ORDER BY code, date
            """,
            (dt_codes, day, day),
        )
        for code, d in cur.fetchall():
            prior_lu.setdefault(code, []).append(d)
    limit_downs = []
    for code, name, industry, pct, first_seal, breaks, board_days, circ in dt_rows:
        series = dt_bars.get(code, [])
        recent = []
        for i, bar in enumerate(series[-6:]):
            idx = len(series) - len(series[-6:]) + i
            prev = [b["volume"] for b in series[max(0, idx - 5):idx] if b["volume"]]
            ratio = None
            if prev and bar["volume"]:
                ratio = round(bar["volume"] / (sum(prev) / len(prev)), 2)
            recent.append({
                "date": bar["date"],
                "pct": None if bar["pct"] is None else round(float(bar["pct"]), 2),
                "vol_ratio": ratio,
            })
        limit_downs.append({
            "code": code,
            "name": name,
            "industry": industry or "",
            "pct": None if pct is None else round(float(pct), 2),
            "circ_mv_yi": None if circ is None else round(float(circ), 2),
            "first_seal_time": first_seal,
            "break_times": breaks,
            "board_days_cumulative": board_days,
            "prior_limit_ups": prior_lu.get(code, []),
            "themes": dt_themes.get(code, []),
            "recent": recent,
            "intraday": _intraday(dt_minutes.get(code, [])),
        })
    existing = _existing(cur)
    conn.close()
    return {
        "as_of": day,
        "n": len(stocks),
        "n_limit_down": len(limit_downs),
        "note": (
            "这些数字只是证据。合力还是主力要看同一题材有没有一批票一起封、日K是群体走势还是单票自己的路径，不按流通市值切。"
            "circ_mv_yi 只是市值，单位亿。volume_shift 是近10日里第一次放到1.5倍的日子。"
            "top_amount_minutes 是当天成交额最大的三分钟，next_5bars_pct 是这之后5根分钟线的价格变化。"
            "分时为空就写分时缺失，不要猜哪一分钟。正文要写成分析，不要把这些数字铺成清单。"
        ),
        "existing_iterative": existing,
        "stocks": stocks,
        "limit_downs": limit_downs,
    }


def _bad_text(text: str) -> str | None:
    for w in BANNED:
        if w in text:
            return w
    return None


def commit(payload: dict) -> dict:
    as_of = str(payload.get("as_of") or "")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", as_of):
        raise SystemExit("as_of 必须是 YYYY-MM-DD")
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        raise SystemExit("items 不能为空")

    reader = _conn()
    cur = reader.cursor()
    day = _day(cur, as_of)
    cur.execute("SELECT code FROM zt_pool WHERE date = %s", (day,))
    pool = {r[0] for r in cur.fetchall()}
    if not pool:
        reader.close()
        raise SystemExit(f"{day} 没有涨停记录")

    seen: set[str] = set()
    dup = []
    for it in items:
        for code in it.get("codes") or []:
            if code in seen:
                dup.append(code)
            seen.add(code)
    missing = sorted(pool - seen)
    extra = sorted(seen - pool)
    if dup or missing or extra:
        reader.close()
        raise SystemExit(json.dumps({
            "error": "涨停必须全部覆盖，且每只只出现一次",
            "duplicate": dup,
            "missing": missing,
            "not_in_pool": extra,
        }, ensure_ascii=False))

    cur.execute(
        """
        SELECT cognition_id FROM cognition
        WHERE type = 'constitution' AND status = 'active'
          AND cognition_id ~ '^F-[0-9]{3}$'
        """
    )
    f_ids = {r[0] for r in cur.fetchall()}
    existing = {row["title"]: row for row in _existing(cur)}
    cur.execute(
        """
        SELECT cognition_id FROM cognition
        WHERE cognition_id ~ '^H-[0-9]{3}$'
        """
    )
    used = {r[0] for r in cur.fetchall()}
    reader.close()

    nxt = 1
    for cid in used:
        nxt = max(nxt, int(cid.split("-")[1]) + 1)

    written = []
    conn = _conn("d12")
    wcur = conn.cursor()
    for it in items:
        title = str(it.get("title") or "").strip()
        statement = str(it.get("statement") or "").strip()
        why = str(it.get("why") or "").strip()
        codes = list(it.get("codes") or [])
        themes = list(it.get("themes") or [])
        derives = list(it.get("derives_from") or [])
        falsify = str(it.get("falsify") or "").strip()
        if not title or not statement or not why or not falsify:
            conn.close()
            raise SystemExit(f"标题、陈述、为什么、证伪都不能空：{title or '(无标题)'}")
        hit = _bad_text(title + statement + why + falsify)
        if hit:
            conn.close()
            raise SystemExit(f"「{title}」里有「{hit}」，迭代认知不写买卖")
        bad_f = [x for x in derives if x not in f_ids]
        if bad_f:
            conn.close()
            raise SystemExit(f"derives_from 只能引用在库的基础认知：{bad_f}")
        sample = {
            "date": day,
            "codes": codes,
            "themes": themes,
            "why": why,
            "n": len(codes),
        }
        prev = existing.get(title)
        if prev:
            if day in prev["dates"]:
                written.append({
                    "cognition_id": prev["cognition_id"],
                    "version": prev["version"],
                    "action": "already",
                    "title": title,
                })
                continue
            wcur.execute(
                """
                SELECT validations, statement, falsifications, derives_from
                FROM cognition
                WHERE cognition_id = %s AND version = %s
                """,
                (prev["cognition_id"], prev["version"]),
            )
            validations, old_statement, old_falsify, old_derives = wcur.fetchone()
            vals = list(validations or [])
            vals.append(sample)
            version = prev["version"] + 1
            wcur.execute(
                """
                INSERT INTO cognition (
                    cognition_id, version, type, title, statement, source,
                    confidence, validations, falsifications, derives_from,
                    status, actor)
                VALUES (%s, %s, 'iterative', %s, %s, %s,
                        NULL, %s::jsonb, %s::jsonb, %s::jsonb,
                        'candidate', 'yan')
                """,
                (
                    prev["cognition_id"], version, title,
                    statement or old_statement,
                    f"yan当日涨停反思 {day}",
                    json.dumps(vals, ensure_ascii=False),
                    json.dumps({"text": falsify}, ensure_ascii=False) if falsify else old_falsify,
                    json.dumps(derives or old_derives or [], ensure_ascii=False),
                ),
            )
            written.append({
                "cognition_id": prev["cognition_id"],
                "version": version,
                "action": "iterate",
                "title": title,
                "n": len(codes),
                "dates": len(vals),
            })
            continue
        if nxt > 999:
            conn.close()
            raise SystemExit("H- 编号已经用完")
        cid = f"H-{nxt:03d}"
        nxt += 1
        wcur.execute(
            """
            INSERT INTO cognition (
                cognition_id, version, type, title, statement, source,
                confidence, validations, falsifications, derives_from,
                status, actor)
            VALUES (%s, 1, 'iterative', %s, %s, %s,
                    NULL, %s::jsonb, %s::jsonb, %s::jsonb,
                    'candidate', 'yan')
            """,
            (
                cid, title, statement, f"yan当日涨停反思 {day}",
                json.dumps([sample], ensure_ascii=False),
                json.dumps({"text": falsify}, ensure_ascii=False),
                json.dumps(derives, ensure_ascii=False),
            ),
        )
        written.append({
            "cognition_id": cid, "version": 1, "action": "create",
            "title": title, "n": len(codes),
        })
    conn.commit()
    conn.close()
    return {"as_of": day, "written": written}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["pack", "commit"])
    ap.add_argument("--date", default="")
    ap.add_argument("--file", default="", help="commit 用的 JSON 路径；省略则读标准输入")
    args = ap.parse_args()
    if args.action == "pack":
        print(json.dumps(pack(args.date or None), ensure_ascii=False, indent=2))
        return
    raw = Path(args.file).read_text() if args.file else sys.stdin.read()
    payload = json.loads(raw)
    print(json.dumps(commit(payload), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
