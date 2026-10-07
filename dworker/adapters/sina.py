"""
新浪行情适配器
行情/外汇/外期/期权接口。
"""
import logging
import requests

from .base import BaseAdapter
from dworker.core.degradation import (
    JobContext, FetchResult, SourceError, SourceErrorKind
)

logger = logging.getLogger(__name__)


class SinaAdapter(BaseAdapter):
    source_name = "sina"

    HQ_URL = "https://hq.sinajs.cn/list="
    FOREX_URL = "https://hq.sinajs.cn/fx/"
    FUTURES_URL = "https://hq.sinajs.cn/futures/"

    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://finance.sina.com.cn/"
        })

    def fetch(self, job_ctx: JobContext, params: dict) -> FetchResult:
        try:
            domain = job_ctx.domain
            if domain == "D7":
                rows = self._fetch_global(params)
            elif domain == "D11":
                rows = self._fetch_option(params)
            else:
                rows = self._fetch_quote(params)

            return FetchResult(source=self.source_name, rows=rows, raw_payload=rows)
        except requests.exceptions.Timeout:
            raise SourceError(SourceErrorKind.NETWORK, "Timeout", self.source_name)
        except requests.exceptions.ConnectionError:
            raise SourceError(SourceErrorKind.NETWORK, "Connection failed", self.source_name)
        except Exception as e:
            raise SourceError(SourceErrorKind.NETWORK, str(e), self.source_name)

    def _fetch_global(self, params: dict) -> list:
        """Fetch global market data (forex, futures, indices)."""
        codes = params.get("codes", [])
        rows = []
        for code in codes:
            try:
                sina_code = self._to_sina_global_code(code)
                if not sina_code:
                    continue

                url = f"{self.HQ_URL}{sina_code}"
                resp = self.session.get(url, timeout=self.timeout)
                if resp.status_code == 200 and resp.text.strip():
                    parsed = self._parse_sina_hq(resp.text, code)
                    if parsed:
                        rows.append(parsed)
            except Exception as e:
                logger.warning(f"Sina global fetch failed for {code}: {e}")
        return rows

    def _fetch_option(self, params: dict) -> list:
        """Fetch option data."""
        # Placeholder for option data fetching
        return []

    def _fetch_quote(self, params: dict) -> list:
        """Fetch A-share quotes."""
        codes = params.get("codes", [])
        rows = []
        for code in codes:
            try:
                sina_code = self._to_sina_code(code)
                url = f"{self.HQ_URL}{sina_code}"
                resp = self.session.get(url, timeout=self.timeout)
                if resp.status_code == 200 and resp.text.strip():
                    parsed = self._parse_sina_a_share(resp.text, code)
                    if parsed:
                        rows.append(parsed)
            except Exception as e:
                logger.warning(f"Sina quote fetch failed for {code}: {e}")
        return rows

    def _to_sina_code(self, code: str) -> str:
        """Convert sh600519 → sh600519 (sina uses same format)"""
        return code  # Sina uses same sh/sz prefix format

    def _to_sina_global_code(self, code: str) -> str:
        """Map canonical global codes to sina codes."""
        mapping = {
            "US10Y": "int_us10y",
            "NK225": "int_nikkei",
            "DXY": "fx_susdindex",
            "USDCNH": "fx_susdcnh",
            "USDJPY": "fx_susdjpy",
        }
        return mapping.get(code, f"hf_{code}")

    def _parse_sina_hq(self, text: str, code: str) -> dict:
        """Parse sina hq response for global markets."""
        try:
            # Format: var hq_str_xxx="name,price,...";
            if '="' not in text:
                return None
            data_str = text.split('="')[1].rstrip('";')
            parts = data_str.split(",")
            if len(parts) >= 3:
                return {
                    "code": code,
                    "name": parts[0],
                    "close": float(parts[1]) if parts[1] else None,
                    "pct": float(parts[2]) if len(parts) > 2 and parts[2] else None,
                }
        except Exception as e:
            logger.warning(f"Parse sina hq error for {code}: {e}")
        return None

    def _parse_sina_a_share(self, text: str, code: str) -> dict:
        """Parse sina A-share quote response."""
        try:
            if '="' not in text:
                return None
            data_str = text.split('="')[1].rstrip('";')
            parts = data_str.split(",")
            if len(parts) >= 32:
                return {
                    "code": code,
                    "name": parts[0],
                    "open": float(parts[1]) if parts[1] else None,
                    "close": float(parts[3]) if parts[3] else None,  # current price
                    "high": float(parts[4]) if parts[4] else None,
                    "low": float(parts[5]) if parts[5] else None,
                    "volume": float(parts[8]) if parts[8] else None,
                    "amount": float(parts[9]) if parts[9] else None,
                }
        except Exception as e:
            logger.warning(f"Parse sina A-share error for {code}: {e}")
        return None

    def probe_schema(self, rows: list) -> bool:
        if not rows:
            return False
        return isinstance(rows[0], dict) and ("close" in rows[0] or "code" in rows[0])
