"""
东财行情适配器
push2/push2his/push2ex 接口。限速 0.5rps burst 2。
"""
import logging
import requests

from .base import BaseAdapter
from dworker.core.degradation import (
    JobContext, FetchResult, SourceError, SourceErrorKind
)

logger = logging.getLogger(__name__)


class EastmoneyAdapter(BaseAdapter):
    source_name = "eastmoney"

    PUSH2_URL = "https://push2.eastmoney.com/api/qt/stock/get"
    PUSH2HIS_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    PUSH2EX_URL = "https://push2ex.eastmoney.com/getTopicZTPool"
    SPOT_URL = "https://push2.eastmoney.com/api/qt/clist/get"

    def __init__(self, timeout: int = 15):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://quote.eastmoney.com/"
        })

    def fetch(self, job_ctx: JobContext, params: dict) -> FetchResult:
        try:
            domain = job_ctx.domain
            if domain == "D2" and params.get("snapshot"):
                rows = self._fetch_spot_snapshot(params)
            elif domain in ("D1", "D2"):
                rows = self._fetch_kline(params)
            elif domain == "D3":
                rows = self._fetch_zt_pool(params)
            else:
                rows = self._fetch_generic(params)

            return FetchResult(source=self.source_name, rows=rows, raw_payload=rows)
        except requests.exceptions.Timeout:
            raise SourceError(SourceErrorKind.NETWORK, "Timeout", self.source_name)
        except requests.exceptions.ConnectionError:
            raise SourceError(SourceErrorKind.NETWORK, "Connection failed", self.source_name)
        except Exception as e:
            raise SourceError(SourceErrorKind.NETWORK, str(e), self.source_name)

    def _fetch_spot_snapshot(self, params: dict) -> list:
        """Fetch full market spot snapshot (stock_zh_a_spot_em equivalent)."""
        rows = []
        try:
            resp = self.session.get(self.SPOT_URL, params={
                "pn": 1, "pz": 5000, "po": 1, "np": 1, "fltt": 2, "invt": 2,
                "fid": "f3", "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048",
                "fields": "f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f14,f15,f16,f17,f18,f20,f21"
            }, timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("data", {}).get("diff", [])
                for item in items:
                    rows.append({
                        "code": item.get("f12", ""),
                        "name": item.get("f14", ""),
                        "close": item.get("f2"),
                        "pct": item.get("f3"),
                        "volume": item.get("f5"),
                        "amount": item.get("f6"),
                        "turnover_rate": item.get("f8"),
                        "pe_ttm": item.get("f9"),
                        "total_mv": item.get("f20"),
                        "circ_mv": item.get("f21"),
                    })
        except Exception as e:
            logger.warning(f"Eastmoney spot snapshot failed: {e}")
        return rows

    def _fetch_kline(self, params: dict) -> list:
        """Fetch K-line data."""
        codes = params.get("codes", [])
        rows = []
        for code in codes:
            try:
                secid = self._to_eastmoney_secid(code)
                resp = self.session.get(self.PUSH2HIS_URL, params={
                    "secid": secid, "fields1": "f1,f2,f3,f4,f5,f6",
                    "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
                    "klt": 101, "fqt": 1, "beg": params.get("start", "0"),
                    "end": params.get("end", "20500101"),
                }, timeout=self.timeout)
                if resp.status_code == 200:
                    data = resp.json()
                    klines = data.get("data", {}).get("klines", [])
                    for line in klines:
                        parts = line.split(",")
                        if len(parts) >= 7:
                            rows.append({
                                "date": parts[0],
                                "code": code,
                                "open": float(parts[1]),
                                "close": float(parts[2]),
                                "high": float(parts[3]),
                                "low": float(parts[4]),
                                "volume": float(parts[5]),
                                "amount": float(parts[6]),
                            })
            except Exception as e:
                logger.warning(f"Eastmoney kline failed for {code}: {e}")
        return rows

    def _fetch_zt_pool(self, params: dict) -> list:
        """Fetch 涨停池 from push2ex."""
        rows = []
        try:
            date = params.get("date", "")
            resp = self.session.get(self.PUSH2EX_URL, params={
                "ut": "7eea3edcaed734bea9cb3f8e2b6b8753",
                "dpt": "wz.ztzt", "Ession": date,
            }, timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("data", {}).get("pool", [])
                for item in items:
                    rows.append({
                        "date": date,
                        "code": item.get("c", ""),
                        "name": item.get("n", ""),
                        "close": item.get("ztp"),
                        "pct": item.get("zdf"),
                        "amount": item.get("amount"),
                        "seal_amount": item.get("funds"),
                    })
        except Exception as e:
            logger.warning(f"Eastmoney ZT pool failed: {e}")
        return rows

    def _fetch_generic(self, params: dict) -> list:
        return []

    def _to_eastmoney_secid(self, code: str) -> str:
        """Convert sh600519 → 1.600519, sz000001 → 0.000001"""
        if code.startswith("sh"):
            return f"1.{code[2:]}"
        elif code.startswith("sz"):
            return f"0.{code[2:]}"
        elif code.startswith("bj"):
            return f"0.{code[2:]}"
        return code

    def probe_schema(self, rows: list) -> bool:
        if not rows:
            return False
        return isinstance(rows[0], dict) and ("close" in rows[0] or "code" in rows[0])
