#!/usr/bin/env python3
"""D8 裁决实测探针：试调一条龙虎端点（梁总 2026-10-08 授权）。
只输出 HTTP 状态/errcode/行数/脱敏样例，绝不打印凭证。
用法: python3 tools/smoke_longhu_one.py [DailyLimitResumption|YouZiDongXiang|Emotion|Radar]
"""
import json
import sys

import requests
import yaml
from pathlib import Path

SECRETS = Path(__file__).resolve().parent.parent / "configs" / "secrets.yaml"

EP = {
    "DailyLimitResumption": {"host": "apphwhq", "a": "DailyLimitResumption", "c": "GetPlateInfo_w38", "auth": "device_3167791"},
    "YouZiDongXiang": {"host": "applhb", "a": "YouZiDongXiangByList", "c": "Index", "auth": "account_3965820"},
    "Emotion": {"host": "apphis", "a": "GetMoneyDate", "c": "Emotion", "auth": "emotion_device"},
    "Radar": {"host": "apphwhq", "a": "Radar", "c": "HomeDingPan", "auth": "device_3167791"},
    "DongXiang": {"host": "applhb", "a": "YouZiDongXiangByList", "c": "Index", "auth": "account_3965820"},
}

endpoint = sys.argv[1] if len(sys.argv) > 1 else "DailyLimitResumption"
cfg = yaml.safe_load(SECRETS.read_text()).get("longhu", {})
ep = EP[endpoint]

auth = {}
if ep["auth"] == "device_3167791":
    auth = {"DeviceID": cfg["account_3167791"]["device_id"]}
elif ep["auth"] == "account_3965820":
    a = cfg["account_3965820"]
    auth = {"UserID": a["user_id"], "Token": a["token"], "DeviceID": a["device_id"]}
elif ep["auth"] == "emotion_device":
    auth = {"DeviceID": cfg["emotion_device_id"]}

params = {"a": ep["a"], "c": ep["c"], "PhoneOSNew": "1", "VerSion": "5.21.0.0", "apiv": "w42"}
params.update(auth)
url = cfg["hosts"][ep["host"]]
headers = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36",
    "Host": ep["host"] + ".longhuvip.com",
    "Connection": "Keep-Alive",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
}

r = requests.post(url, data=params, headers=headers, timeout=15)
print("endpoint:", endpoint, "| HTTP", r.status_code)
d = r.json()
print("errcode:", d.get("errcode"), "| errmsg:", str(d.get("errmsg"))[:80])


def count_rows(o):
    """递归计数，兼容 list / ZY / DongXiang / data / List 等多键格式。"""
    if isinstance(o, list):
        return len(o)
    if isinstance(o, dict):
        # Z7: 补充 ZY / DongXiang 键（Emotion/DongXiang 端点）
        for k in ("data", "Data", "list", "List", "result", "Result", "ZY", "DongXiang"):
            v = o.get(k)
            if isinstance(v, list):
                return len(v)
            if isinstance(v, dict):
                n = count_rows(v)
                if n:
                    return n
        return max([count_rows(v) for v in o.values()] or [0])
    return 0


def first_row(o):
    if isinstance(o, list) and o and isinstance(o[0], dict):
        return o[0]
    if isinstance(o, dict):
        for v in o.values():
            fr = first_row(v)
            if fr:
                return fr
    return None


print("rows:", count_rows(d))
fr = first_row(d)
if fr:
    print("first_row_keys:", list(fr.keys())[:15])
    print("sample(masked):", json.dumps({k: str(v)[:20] for k, v in list(fr.items())[:6]}, ensure_ascii=False))
