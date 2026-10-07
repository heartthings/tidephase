"""
通达信 mootdx 适配器
连接池 ≤4 并发。K线/指数/财务数据。
"""
import logging

from .base import BaseAdapter
from dworker.core.degradation import (
    JobContext, FetchResult, SourceError, SourceErrorKind
)

logger = logging.getLogger(__name__)


class MootdxAdapter(BaseAdapter):
    source_name = "mootdx"

    def __init__(self):
        self._api = None

    def _get_api(self):
        if self._api is None:
            try:
                from mootdx.quotes import Quotes
                self._api = Quotes.factory(market='std')
            except ImportError:
                raise SourceError(SourceErrorKind.NETWORK,
                                  "mootdx not installed", self.source_name)
            except Exception as e:
                raise SourceError(SourceErrorKind.NETWORK,
                                  f"mootdx connection failed: {e}", self.source_name)
        return self._api

    def fetch(self, job_ctx: JobContext, params: dict) -> FetchResult:
        try:
            domain = job_ctx.domain
            if domain == "D1":
                rows = self._fetch_index(params)
            elif domain == "D2":
                rows = self._fetch_stock(params)
            elif domain == "D9":
                rows = self._fetch_f10(params)
            else:
                rows = self._fetch_generic(params)

            return FetchResult(source=self.source_name, rows=rows, raw_payload=rows)
        except SourceError:
            raise
        except Exception as e:
            raise SourceError(SourceErrorKind.NETWORK, str(e), self.source_name)

    def _fetch_index(self, params: dict) -> list:
        """Fetch index daily K-line."""
        api = self._get_api()
        codes = params.get("codes", [])
        rows = []
        for code in codes:
            try:
                # mootdx uses different market codes for indices
                symbol = code[2:]  # strip sh/sz prefix
                market = 1 if code.startswith("sh") else 0
                data = api.bars(category=9, market=market, code=symbol, count=320)
                if data is not None and not data.empty:
                    for _, row in data.iterrows():
                        rows.append({
                            "date": str(row.get("datetime", ""))[:10],
                            "code": code,
                            "open": float(row.get("open", 0)),
                            "close": float(row.get("close", 0)),
                            "high": float(row.get("high", 0)),
                            "low": float(row.get("low", 0)),
                            "volume": float(row.get("vol", 0)),
                            "amount": float(row.get("amount", 0)),
                        })
            except Exception as e:
                logger.warning(f"mootdx index fetch failed for {code}: {e}")
        return rows

    def _fetch_stock(self, params: dict) -> list:
        """Fetch stock daily K-line."""
        api = self._get_api()
        codes = params.get("codes", [])
        rows = []
        for code in codes:
            try:
                symbol = code[2:]
                market = 1 if code.startswith("sh") else 0
                data = api.bars(category=9, market=market, code=symbol, count=320)
                if data is not None and not data.empty:
                    for _, row in data.iterrows():
                        rows.append({
                            "date": str(row.get("datetime", ""))[:10],
                            "code": code,
                            "open": float(row.get("open", 0)),
                            "close": float(row.get("close", 0)),
                            "high": float(row.get("high", 0)),
                            "low": float(row.get("low", 0)),
                            "volume": float(row.get("vol", 0)),
                            "amount": float(row.get("amount", 0)),
                        })
            except Exception as e:
                logger.warning(f"mootdx stock fetch failed for {code}: {e}")
        return rows

    def _fetch_f10(self, params: dict) -> list:
        """Fetch F10 financial data."""
        # Placeholder - mootdx F10 interface
        return []

    def _fetch_generic(self, params: dict) -> list:
        return []

    def probe_schema(self, rows: list) -> bool:
        if not rows:
            return False
        row = rows[0]
        return isinstance(row, dict) and "close" in row
