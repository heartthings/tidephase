#!/usr/bin/env python3
"""
观势数据层 API · Python 客户端样例
用法：
    python3 tools/data_api_client_example.py

依赖：pip install requests pyyaml
凭证：从 configs/secrets.yaml 读取 bearer_token_read
API 地址：127.0.0.1:8787（永不公网）
"""
import csv
import io
import json
import sys
from pathlib import Path

import requests
import yaml

# ─── 配置 ────────────────────────────────────────────────────────────

API_BASE = "http://127.0.0.1:8787"
SECRETS_PATH = Path(__file__).resolve().parent.parent / "configs" / "secrets.yaml"


def get_token(role: str = "read") -> str:
    """从 secrets.yaml 读取 bearer token。"""
    secrets = yaml.safe_load(SECRETS_PATH.read_text()) or {}
    api_cfg = secrets.get("api", {})
    key = f"bearer_token_{role}"
    token = api_cfg.get(key, "")
    if not token:
        print(f"ERROR: {key} not found in secrets.yaml")
        sys.exit(1)
    return token


# ─── 通用请求 ─────────────────────────────────────────────────────────

class GuanshiClient:
    """观势数据层 API 客户端。"""

    def __init__(self, base_url: str = API_BASE, token: str = None):
        self.base_url = base_url.rstrip("/")
        self.token = token or get_token("read")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
        })

    def _get(self, path: str, params: dict = None) -> dict:
        resp = self.session.get(f"{self.base_url}{path}", params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _get_csv(self, path: str, params: dict = None) -> str:
        params = params or {}
        params["format"] = "csv"
        resp = self.session.get(f"{self.base_url}{path}", params=params, timeout=30)
        resp.raise_for_status()
        return resp.text

    # ─── E1 /health ──────────────────────────────────────────────────
    def health(self) -> dict:
        return self._get("/health")

    # ─── E2 /meta/tables ─────────────────────────────────────────────
    def list_tables(self) -> list:
        resp = self._get("/meta/tables")
        return resp.get("data", [])

    # ─── E3 /meta/trade_cal ──────────────────────────────────────────
    def trade_calendar(self, market: str = "CN", start: str = None, end: str = None) -> list:
        params = {"market": market}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        resp = self._get("/meta/trade_cal", params)
        return resp.get("data", [])

    # ─── E4 /meta/instruments ────────────────────────────────────────
    def instruments(self, keyword: str = None, market: str = None) -> list:
        params = {}
        if keyword:
            params["keyword"] = keyword
        if market:
            params["market"] = market
        resp = self._get("/meta/instruments", params)
        return resp.get("data", [])

    # ─── E5 /data/{table} ────────────────────────────────────────────
    def query_table(self, table: str, start: str = None, end: str = None,
                    codes: str = None, fields: str = None,
                    limit: int = 100, order: str = "desc") -> dict:
        params = {"limit": limit, "order": order}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        if codes:
            params["codes"] = codes
        if fields:
            params["fields"] = fields
        return self._get(f"/data/{table}", params)

    def query_table_csv(self, table: str, **kwargs) -> str:
        params = {k: v for k, v in kwargs.items() if v is not None}
        return self._get_csv(f"/data/{table}", params)

    # ─── E6 /data/sentiment/latest ───────────────────────────────────
    def sentiment_latest(self, n: int = 5) -> list:
        resp = self._get("/data/sentiment/latest", {"n": n})
        return resp.get("data", [])

    # ─── E7 /data/global/overnight ───────────────────────────────────
    def global_overnight(self, date: str = None) -> list:
        params = {}
        if date:
            params["date"] = date
        resp = self._get("/data/global/overnight", params)
        return resp.get("data", [])

    # ─── E16 /ingest/status ──────────────────────────────────────────
    def ingest_status(self, job: str = None, date: str = None) -> list:
        params = {}
        if job:
            params["job"] = job
        if date:
            params["date"] = date
        resp = self._get("/ingest/status", params)
        return resp.get("data", [])

    # ─── 分页遍历 ────────────────────────────────────────────────────
    def paginate(self, table: str, page_size: int = 1000, **kwargs):
        """自动翻页，返回生成器。"""
        cursor = None
        while True:
            params = {**kwargs, "limit": page_size}
            if cursor:
                params["cursor"] = cursor
            resp = self._get(f"/data/{table}", params)
            data = resp.get("data", [])
            yield from data
            cursor = resp.get("meta", {}).get("next_cursor")
            if not cursor or len(data) < page_size:
                break


# ─── Demo ─────────────────────────────────────────────────────────────

def main():
    client = GuanshiClient()

    # 1. Health check
    print("=== Health ===")
    print(json.dumps(client.health(), indent=2, ensure_ascii=False))

    # 2. List tables
    print("\n=== Tables (first 10) ===")
    tables = client.list_tables()
    for t in tables[:10]:
        print(f"  {t}")
    print(f"  ... total {len(tables)} tables")

    # 3. Trade calendar
    print("\n=== Trade Calendar (SSE, Oct 2026) ===")
    cal = client.trade_calendar(market="SSE", start="2026-10-01", end="2026-10-15")
    for row in cal:
        status = "OPEN" if row.get("is_open") else "CLOSED"
        print(f"  {row['cal_date']}  {status}")

    # 4. Stock daily sample
    print("\n=== stock_daily (latest 5 rows) ===")
    resp = client.query_table("stock_daily", limit=5)
    for row in resp.get("data", []):
        print(f"  {row.get('date')} {row.get('code')} close={row.get('close')} pct={row.get('pct')}")
    print(f"  meta: rows={resp.get('meta',{}).get('rows')}")

    # 5. Global overnight
    print("\n=== Global Overnight ===")
    for row in client.global_overnight():
        print(f"  {row.get('market'):10s} {row.get('code'):5s} {row.get('name'):8s} close={row.get('close')}")

    # 6. CSV export example
    print("\n=== CSV Export (index_daily) ===")
    csv_text = client.query_table_csv("index_daily", start="2026-10-08", end="2026-10-09")
    reader = csv.DictReader(io.StringIO(csv_text))
    for i, row in enumerate(reader):
        if i < 3:
            print(f"  {row.get('date')} {row.get('code')} close={row.get('close')}")
    print(f"  ... (CSV rows: {sum(1 for _ in reader) + 3})")


if __name__ == "__main__":
    main()
