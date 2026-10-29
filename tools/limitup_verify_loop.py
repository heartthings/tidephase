#!/usr/bin/env python3
"""首板/二板预测闭环：落库 → 次日核对 → 反思。

1. persist：把 predict_limitup 的候选写成 prediction（category=first_board/second_board）
2. verify：到了 check_date，用 zt_pool 判定 hit/miss
3. reflect：把 miss 和「未点名却涨停」写进 reflection，供下次简报引用

不荐股。概率是历史晋级率，核对结果只用于校准与反思。
"""
from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import psycopg2
import yaml

SECRETS = Path(__file__).resolve().parent.parent / "configs" / "secrets.yaml"
TOKEN = Path("/home/hello/.qwenpaw/workspaces/guanshi/data/data_api_read_token")
API = "http://127.0.0.1:8787/data/predict_limitup?format=json"
WRITE_API = "http://127.0.0.1:8787"
TZ = timezone(timedelta(hours=8))


def _secrets():
    return yaml.safe_load(SECRETS.read_text())


def _conn(role="reader"):
    sec = _secrets()["database"]
    if role == "d12":
        user, key = "duser_d12writer", "duser_d12writer_password"
    elif role == "writer":
        user, key = "duser_writer", "duser_writer_password"
    else:
        user, key = "duser_reader", "duser_reader_password"
    return psycopg2.connect(
        host="127.0.0.1", port=15432, dbname="market_tsdb",
        user=user, password=sec[key],
    )


def _token(kind="read"):
    sec = _secrets()["api"]
    return sec["bearer_token_write" if kind == "write" else "bearer_token_read"]


def _api_json(path_or_url, method="GET", body=None, write=False):
    url = path_or_url if path_or_url.startswith("http") else f"{WRITE_API}{path_or_url}"
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode()
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={
            "Authorization": f"Bearer {_token('write' if write else 'read')}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode())


def _predict(as_of: str | None = None):
    token = TOKEN.read_text().strip()
    url = API if not as_of else f"{API}&date={as_of}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode())["data"]


def _code6(code: str) -> str:
    s = str(code or "")
    return s[2:] if s[:2] in ("sh", "sz", "bj") else s


def persist(result: dict | None = None, as_of: str | None = None) -> dict:
    result = result or _predict(as_of)
    as_of = result["as_of"]
    nxt = result.get("next_trade_date")
    if not nxt:
        return {"persisted": 0, "note": "next_trade_date unknown"}
    created = []
    for kind, key in (("second_board", "second_board"), ("first_board", "first_board")):
        for g in (result.get(key) or {}).get("groups") or []:
            for c in g.get("candidates") or []:
                code = c["code"]
                pid = f"LU-{as_of.replace('-', '')}-{kind[:1].upper()}-{_code6(code)}"
                statement = (
                    f"{as_of} 收盘 → {nxt}：{c['name']}（{code}）入选{('二板' if kind=='second_board' else '首板')}候选，"
                    f"题材 {g.get('theme') or ''}，概率 {c.get('prob')}%"
                )
                body = {
                    "prediction_id": pid,
                    "statement": statement,
                    "category": kind,
                    "confidence_pct": int(round(float(c.get("prob") or 0))),
                    "check_date": nxt,
                    "horizon": "T1",
                    "falsify": {
                        "metric": "zt_pool.code",
                        "code": code,
                        "direction": "present",
                        "as_of": as_of,
                        "kind": kind,
                        "prob": c.get("prob"),
                        "theme": g.get("theme"),
                        "name": c.get("name"),
                        "reasons": c.get("reasons") or [],
                    },
                    "conditions": ["F-011", "F-024", "F-025"],
                    "actor": "yan",
                    "source": "predict_limitup",
                    "regime_at_create": (result.get("market") or {}).get("sentiment"),
                }
                try:
                    _api_json("/d12/prediction", method="POST", body=body, write=True)
                    created.append(pid)
                except urllib.error.HTTPError as e:
                    err = e.read().decode("utf-8", "replace")
                    if e.code == 409 or "CONFLICT" in err:
                        continue
                    raise RuntimeError(err) from e
    return {"persisted": len(created), "as_of": as_of, "check_date": nxt, "ids": created}


def verify(check_date: str | None = None) -> dict:
    conn = _conn("d12")
    day = check_date or date.today().isoformat()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT prediction_id, falsify, confidence_pct, statement
            FROM prediction
            WHERE category IN ('first_board', 'second_board')
              AND result = 'pending'
              AND check_date <= %s
            """,
            (day,),
        )
        rows = cur.fetchall()
        cur.execute("SELECT code FROM zt_pool WHERE date = %s", (day,))
        zt = {r[0] for r in cur.fetchall()}
        hits, misses = [], []
        for pid, falsify, conf, statement in rows:
            fz = falsify if isinstance(falsify, dict) else json.loads(falsify or "{}")
            code = fz.get("code")
            hit = code in zt
            result = "hit" if hit else "miss"
            note = (
                f"{day} zt_pool{'命中' if hit else '未涨停'}；预测概率 {conf}%"
            )
            cur.execute(
                """
                UPDATE prediction
                SET result=%s, result_note=%s, checked_at=now(), writeback_done=true
                WHERE prediction_id=%s AND result='pending'
                """,
                (result, note, pid),
            )
            (hits if hit else misses).append({
                "prediction_id": pid, "code": code, "prob": conf,
                "name": fz.get("name"), "theme": fz.get("theme"),
                "kind": fz.get("kind"), "reasons": fz.get("reasons") or [],
            })
    conn.commit()
    conn.close()
    return {"check_date": day, "hits": hits, "misses": misses,
            "n_hit": len(hits), "n_miss": len(misses)}


def reflect(verify_result: dict) -> dict:
    """把 miss 写成反思；并记录当日涨停但未进名单的观察（只记热题材高板，避免全市场噪声）。"""
    day = verify_result["check_date"]
    inserted = []
    records = []
    for m in verify_result.get("misses") or []:
        when = m.get("check_date") or day
        if (m.get("prob") or 0) < 10:
            # 低概率未中只记样本，不降置信度
            lesson_kind = "none"
            stage = "noise"
            lesson = (
                f"{when} {m.get('name')}({m.get('code')}) 预测{m.get('kind')}未涨停。"
                f"概率仅 {m.get('prob')}%，属低置信候选，不降置信度。"
            )
        else:
            lesson_kind = "rule_revision"
            stage = "data_premise"
            lesson = (
                f"{when} {m.get('name')}({m.get('code')}) 预测{m.get('kind')}未涨停，"
                f"概率 {m.get('prob')}%，题材 {m.get('theme')}。"
                f"原由：{'；'.join(m.get('reasons') or []) or '无'}。"
                f"下次同形态同题材要核对：开盘是否已经兑现、题材阶段是否已转分歧、是否缩量。"
            )
        records.append({
            "decision_id": m["prediction_id"],
            "closed_at": datetime.now(TZ).isoformat(),
            "quadrant": "wrong_wrong",
            "error_stage": stage,
            "lesson_text": lesson,
            "lesson_kind": lesson_kind,
            "action_item": (
                f"次日简报引用：{m.get('name')} 未兑现，检查题材阶段与开盘兑现"
                if (m.get("prob") or 0) >= 10 else None
            ),
            "action_status": "open" if (m.get("prob") or 0) >= 10 else "waived",
            "evidence_summary": f"check_date={when} result=miss prob={m.get('prob')}",
            "evidence_refs": {"zt_pool_date": when, "code": m.get("code")},
            "actor": "yan",
        })
    for h in verify_result.get("hits") or []:
        when = h.get("check_date") or day
        records.append({
            "decision_id": h["prediction_id"],
            "closed_at": datetime.now(TZ).isoformat(),
            "quadrant": "right_right",
            "error_stage": None,
            "lesson_text": (
                f"{when} {h.get('name')}({h.get('code')}) 预测{h.get('kind')}兑现。"
                f"概率 {h.get('prob')}%，题材 {h.get('theme')}。"
            ),
            "lesson_kind": "none",
            "action_status": "done",
            "evidence_summary": f"check_date={when} result=hit prob={h.get('prob')}",
            "evidence_refs": {"zt_pool_date": when, "code": h.get("code")},
            "actor": "yan",
        })
    if not records:
        return {"reflections": 0}
    # reflection API requires decision_id in prediction — already true
    try:
        out = _api_json("/reflection", method="POST", body={"records": records}, write=True)
        return {"reflections": out.get("data", {}).get("count") or len(records), "raw": out.get("data")}
    except Exception as e:
        body = e.read().decode() if hasattr(e, "read") else str(e)
        raise RuntimeError(body) from e


def summary(days: int = 20) -> dict:
    conn = _conn("reader")
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT category,
                   count(*) FILTER (WHERE result='hit') AS hits,
                   count(*) FILTER (WHERE result='miss') AS misses,
                   count(*) FILTER (WHERE result='pending') AS pending,
                   round(avg(confidence_pct) FILTER (WHERE result='hit'), 1) AS avg_prob_hit,
                   round(avg(confidence_pct) FILTER (WHERE result='miss'), 1) AS avg_prob_miss
            FROM prediction
            WHERE category IN ('first_board', 'second_board')
              AND check_date >= CURRENT_DATE - %s
            GROUP BY category
            """,
            (days,),
        )
        by_cat = [
            {"category": r[0], "hits": r[1], "misses": r[2], "pending": r[3],
             "avg_prob_hit": float(r[4]) if r[4] is not None else None,
             "avg_prob_miss": float(r[5]) if r[5] is not None else None}
            for r in cur.fetchall()
        ]
        cur.execute(
            """
            SELECT p.prediction_id, p.category, p.confidence_pct, p.result,
                   p.falsify->>'name', p.falsify->>'theme', p.check_date::text,
                   r.lesson_text
            FROM prediction p
            LEFT JOIN LATERAL (
                SELECT lesson_text FROM reflection
                WHERE decision_id = p.prediction_id
                ORDER BY created_at DESC LIMIT 1
            ) r ON true
            WHERE p.category IN ('first_board', 'second_board')
              AND p.result IN ('hit', 'miss')
              AND p.check_date >= CURRENT_DATE - %s
            ORDER BY p.check_date DESC, p.confidence_pct DESC
            LIMIT 40
            """,
            (days,),
        )
        recent = [
            {"id": r[0], "category": r[1], "prob": r[2], "result": r[3],
             "name": r[4], "theme": r[5], "check_date": r[6], "lesson": r[7]}
            for r in cur.fetchall()
        ]
    conn.close()
    return {"window_days": days, "by_category": by_cat, "recent": recent}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["persist", "verify", "reflect", "cycle", "summary"])
    ap.add_argument("--date", default="")
    args = ap.parse_args()
    if args.action == "persist":
        print(json.dumps(persist(as_of=args.date or None), ensure_ascii=False, indent=2))
    elif args.action == "verify":
        print(json.dumps(verify(args.date or None), ensure_ascii=False, indent=2))
    elif args.action == "reflect":
        v = verify(args.date or None)
        print(json.dumps(reflect(v), ensure_ascii=False, indent=2))
    elif args.action == "cycle":
        # 先核对昨天，再落今天
        v = verify(args.date or None)
        r = reflect(v) if (v["n_hit"] + v["n_miss"]) else {"reflections": 0}
        p = persist()
        print(json.dumps({"verify": v, "reflect": r, "persist": p}, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(summary(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
