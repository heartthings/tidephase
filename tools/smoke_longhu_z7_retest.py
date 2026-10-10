#!/usr/bin/env python3
"""
Z7 龙虎实盘重测 · 周一 2026-10-12 开盘后执行
验证 D8 龙虎落地三端点：Emotion / DailyLimitResumption / Radar

用法: python3 tools/smoke_longhu_z7_retest.py
"""
import json
import sys
from datetime import datetime

import requests
import yaml
from pathlib import Path

SECRETS = Path(__file__).resolve().parent.parent / "configs" / "secrets.yaml"

EP = {
    "DailyLimitResumption": {"host": "apphwhq", "a": "DailyLimitResumption", "c": "GetPlateInfo_w38", "auth": "device_3167791"},
    "Emotion": {"host": "apphis", "a": "GetMoneyDate", "c": "Emotion", "auth": "emotion_device"},
    "Radar": {"host": "apphwhq", "a": "Radar", "c": "HomeDingPan", "auth": "device_3167791"},
}


def load_cfg():
    return yaml.safe_load(SECRETS.read_text()).get("longhu", {})


def get_auth(cfg, auth_type):
    if auth_type == "device_3167791":
        return {"DeviceID": cfg["account_3167791"]["device_id"]}
    elif auth_type == "emotion_device":
        return {"DeviceID": cfg["emotion_device_id"]}
    return {}


def call_endpoint(endpoint_name):
    cfg = load_cfg()
    ep = EP[endpoint_name]
    auth = get_auth(cfg, ep["auth"])
    params = {"a": ep["a"], "c": ep["c"], "PhoneOSNew": "1", "VerSion": "5.21.0.0", "apiv": "w42"}
    params.update(auth)
    url = cfg["hosts"][ep["host"]]
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36",
        "Host": ep["host"] + ".longhuvip.com",
        "Connection": "Keep-Alive",
    }
    r = requests.post(url, data=params, headers=headers, timeout=15)
    return r


def count_rows(o):
    if isinstance(o, list):
        return len(o)
    if isinstance(o, dict):
        for k in ("data", "Data", "list", "List", "result", "Result", "ZY", "DongXiang", "nums"):
            v = o.get(k)
            if isinstance(v, list):
                return len(v)
            if isinstance(v, dict):
                n = count_rows(v)
                if n:
                    return n
        return max([count_rows(v) for v in o.values()] or [0])
    return 0


def main():
    print("=" * 60)
    print(f"Z7 龙虎实盘重测 · {datetime.now().isoformat()}")
    print("=" * 60)

    results = {}

    for ep_name in ["Emotion", "DailyLimitResumption", "Radar"]:
        print(f"\n--- {ep_name} ---")
        try:
            r = call_endpoint(ep_name)
            d = r.json()
            errcode = d.get("errcode")
            rows = count_rows(d)
            results[ep_name] = {
                "http_status": r.status_code,
                "errcode": errcode,
                "rows": rows,
                "ok": r.status_code == 200 and errcode == 0 and rows > 0,
            }
            print(f"  HTTP: {r.status_code} | errcode: {errcode} | rows: {rows}")
            if results[ep_name]["ok"]:
                print(f"  ✅ PASS")
            else:
                print(f"  ❌ FAIL")
        except Exception as e:
            print(f"  ❌ ERROR: {e}")
            results[ep_name] = {"ok": False, "error": str(e)}

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    all_ok = all(r.get("ok") for r in results.values())
    for ep_name, r in results.items():
        status = "✅" if r.get("ok") else "❌"
        print(f"  {status} {ep_name}: rows={r.get('rows', 'N/A')}")

    if all_ok:
        print("\n✅ Z7 龙虎实盘重测全部通过")
    else:
        print("\n❌ Z7 龙虎实盘重测有失败项")

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
