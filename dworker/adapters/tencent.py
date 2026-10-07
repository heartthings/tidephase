"""
腾讯行情适配器
qt/ifzq 接口。不封 IP，优先使用。
"""
import logging
import requests
from typing import Optional

from .base import BaseAdapter
from dworker.core.degradation import (
    JobContext, FetchResult, SourceError, SourceErrorKind
)

logger = logging.getLogger(__name__)


class TencentAdapter(BaseAdapter):
    source_name = "tencent"

    QT_URL = "https://qt.gtimg.cn/q="
    IFZQ_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"

    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })

    def fetch(self, job_ctx: JobContext, params: dict) -> FetchResult:
        """
        Fetch from Tencent qt/ifzq.
        params: {codes: [...], kline_params: {...}}
        """
        try:
            domain = job_ctx.domain
            if domain in ("D1", "D2"):
                rows = self._fetch_kline(params)
            elif domain == "D7":
                rows = self._fetch_global(params)
            else:
                rows = self._fetch_quote(params)

            return FetchResult(
                source=self.source_name,
                rows=rows,
                raw_payload=rows
            )
        except requests.exceptions.Timeout:
            raise SourceError(SourceErrorKind.NETWORK, "Request timeout", self.source_name)
        except requests.exceptions.ConnectionError:
            raise SourceError(SourceErrorKind.NETWORK, "Connection failed", self.source_name)
        except Exception as e:
            raise SourceError(SourceErrorKind.NETWORK, str(e), self.source_name)

    def _fetch_kline(self, params: dict) -> list:
        """Fetch K-line data via ifzq API."""
        codes = params.get("codes", [])
        if not codes:
            raise SourceError(SourceErrorKind.EMPTY, "No codes provided", self.source_name)

        rows = []
        for code in codes:
            try:
                resp = self.session.get(
                    self.IFZQ_URL,
                    params={"param": f"{code},day,,,320,qfq",
                            "_var": "kline_dayqfq"},
                    timeout=self.timeout
                )
                if resp.status_code == 200:
                    data = resp.json()
                    # Parse Tencent ifzq response format
                    klines = self._parse_ifzq_response(data, code)
                    rows.extend(klines)
                else:
                    logger.warning(f"Tencent ifzq returned {resp.status_code} for {code}")
            except Exception as e:
                logger.warning(f"Tencent kline fetch failed for {code}: {e}")

        return rows

    def _fetch_global(self, params: dict) -> list:
        """Fetch global market data via qt API."""
        codes = params.get("codes", [])
        rows = []
        for code in codes:
            try:
                resp = self.session.get(
                    f"{self.QT_URL}{code}",
                    timeout=self.timeout
                )
                if resp.status_code == 200 and resp.text.strip():
                    parsed = self._parse_qt_global(resp.text, code)
                    if parsed:
                        rows.append(parsed)
            except Exception as e:
                logger.warning(f"Tencent global fetch failed for {code}: {e}")
        return rows

    def _fetch_quote(self, params: dict) -> list:
        """Fetch real-time quotes via qt API."""
        codes = params.get("codes", [])
        rows = []
        for code in codes:
            try:
                resp = self.session.get(
                    f"{self.QT_URL}{code}",
                    timeout=self.timeout
                )
                if resp.status_code == 200 and resp.text.strip():
                    parsed = self._parse_qt_quote(resp.text, code)
                    if parsed:
                        rows.append(parsed)
            except Exception as e:
                logger.warning(f"Tencent quote fetch failed for {code}: {e}")
        return rows

    def _parse_ifzq_response(self, data: dict, code: str) -> list:
        """Parse Tencent ifzq kline response."""
        rows = []
        try:
            stock_data = data.get("data", {}).get(code, {})
            day_data = stock_data.get("day", stock_data.get("qfqday", []))
            for item in day_data:
                if len(item) >= 6:
                    rows.append({
                        "date": item[0],
                        "code": code,
                        "open": float(item[1]),
                        "close": float(item[2]),
                        "high": float(item[3]),
                        "low": float(item[4]),
                        "volume": float(item[5]) if len(item) > 5 else None,
                    })
        except Exception as e:
            logger.warning(f"Parse error for {code}: {e}")
        return rows

    def _parse_qt_global(self, text: str, code: str) -> dict:
        """Parse qt global market response."""
        try:
            parts = text.strip().split("~")
            if len(parts) >= 5:
                return {
                    "code": code,
                    "name": parts[1] if len(parts) > 1 else None,
                    "close": float(parts[3]) if len(parts) > 3 and parts[3] else None,
                    "pct": float(parts[32]) if len(parts) > 32 and parts[32] else None,
                }
        except Exception as e:
            logger.warning(f"Parse qt global error for {code}: {e}")
        return None

    def _parse_qt_quote(self, text: str, code: str) -> dict:
        """Parse qt real-time quote response."""
        try:
            parts = text.strip().split("~")
            if len(parts) >= 45:
                return {
                    "code": code,
                    "name": parts[1],
                    "close": float(parts[3]) if parts[3] else None,
                    "open": float(parts[5]) if parts[5] else None,
                    "high": float(parts[33]) if parts[33] else None,
                    "low": float(parts[34]) if parts[34] else None,
                    "volume": float(parts[6]) if parts[6] else None,
                    "pct": float(parts[32]) if parts[32] else None,
                }
        except Exception as e:
            logger.warning(f"Parse qt quote error for {code}: {e}")
        return None

    def probe_schema(self, rows: list) -> bool:
        if not rows:
            return False
        row = rows[0]
        return isinstance(row, dict) and "close" in row
