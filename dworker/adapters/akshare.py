"""
AKShare 适配器
串行 + 0.3-1s 随机抖动。内部上游多为东财/新浪。
"""
import logging

from .base import BaseAdapter
from dworker.core.degradation import (
    JobContext, FetchResult, SourceError, SourceErrorKind
)

logger = logging.getLogger(__name__)


class AkshareAdapter(BaseAdapter):
    source_name = "akshare"

    def __init__(self):
        self._ak = None

    def _get_ak(self):
        if self._ak is None:
            try:
                import akshare as ak
                self._ak = ak
            except ImportError:
                raise SourceError(SourceErrorKind.NETWORK,
                                  "akshare not installed", self.source_name)
        return self._ak

    def fetch(self, job_ctx: JobContext, params: dict) -> FetchResult:
        try:
            domain = job_ctx.domain
            job_name = job_ctx.job_name

            if job_name == "j_stock_daily":
                rows = self._fetch_stock_spot(params)
            elif job_name == "j_etf_daily":
                rows = self._fetch_etf_spot(params)
            elif job_name == "j_trade_cal":
                rows = self._fetch_trade_cal(params)
            elif job_name == "j_instrument_master":
                rows = self._fetch_instrument_list(params)
            elif domain == "D7":
                rows = self._fetch_global(params)
            elif domain == "D4":
                rows = self._fetch_fund_flow(params)
            elif domain == "D8":
                rows = self._fetch_macro(params)
            else:
                rows = self._fetch_generic(params)

            return FetchResult(source=self.source_name, rows=rows, raw_payload=rows)
        except SourceError:
            raise
        except Exception as e:
            raise SourceError(SourceErrorKind.NETWORK, str(e), self.source_name)

    def _fetch_stock_spot(self, params: dict) -> list:
        """Fetch full market spot via akshare stock_zh_a_spot_em."""
        ak = self._get_ak()
        rows = []
        try:
            df = ak.stock_zh_a_spot_em()
            if df is not None and not df.empty:
                for _, row in df.iterrows():
                    rows.append({
                        "code": self._to_standard_code(str(row.get("代码", ""))),
                        "name": row.get("名称", ""),
                        "close": float(row.get("最新价", 0) or 0),
                        "pct": float(row.get("涨跌幅", 0) or 0),
                        "volume": float(row.get("成交量", 0) or 0),
                        "amount": float(row.get("成交额", 0) or 0),
                        "turnover_rate": float(row.get("换手率", 0) or 0),
                        "pe_ttm": float(row.get("市盈率-动态", 0) or 0),
                        "total_mv": float(row.get("总市值", 0) or 0),
                        "circ_mv": float(row.get("流通市值", 0) or 0),
                    })
        except Exception as e:
            logger.warning(f"akshare stock spot failed: {e}")
        return rows

    def _fetch_etf_spot(self, params: dict) -> list:
        """Fetch ETF spot data."""
        ak = self._get_ak()
        rows = []
        try:
            df = ak.fund_etf_spot_em()
            if df is not None and not df.empty:
                for _, row in df.iterrows():
                    rows.append({
                        "code": self._to_standard_code(str(row.get("代码", ""))),
                        "name": row.get("名称", ""),
                        "close": float(row.get("最新价", 0) or 0),
                        "pct": float(row.get("涨跌幅", 0) or 0),
                        "volume": float(row.get("成交量", 0) or 0),
                        "amount": float(row.get("成交额", 0) or 0),
                    })
        except Exception as e:
            logger.warning(f"akshare ETF spot failed: {e}")
        return rows

    def _fetch_trade_cal(self, params: dict) -> list:
        """Fetch trade calendar."""
        ak = self._get_ak()
        rows = []
        try:
            df = ak.tool_trade_date_hist_sina()
            if df is not None and not df.empty:
                for _, row in df.iterrows():
                    rows.append({
                        "market": "CN",
                        "cal_date": str(row.get("trade_date", "")),
                        "is_open": 1,
                    })
        except Exception as e:
            logger.warning(f"akshare trade cal failed: {e}")
        return rows

    def _fetch_instrument_list(self, params: dict) -> list:
        """Fetch stock list for instrument_master."""
        ak = self._get_ak()
        rows = []
        try:
            df = ak.stock_info_a_code_name()
            if df is not None and not df.empty:
                for _, row in df.iterrows():
                    code = str(row.get("code", ""))
                    rows.append({
                        "code": self._to_standard_code(code),
                        "name": row.get("name", ""),
                        "market": self._infer_market(code),
                        "inst_type": "stock",
                        "status": "active",
                    })
        except Exception as e:
            logger.warning(f"akshare instrument list failed: {e}")
        return rows

    def _fetch_global(self, params: dict) -> list:
        """Fetch global market data."""
        # akshare has various global index/commodity APIs
        return []

    def _fetch_fund_flow(self, params: dict) -> list:
        """Fetch fund flow data."""
        return []

    def _fetch_macro(self, params: dict) -> list:
        """Fetch macro indicators."""
        return []

    def _fetch_generic(self, params: dict) -> list:
        return []

    def _to_standard_code(self, raw_code: str) -> str:
        """Convert 600519 → sh600519, 000001 → sz000001"""
        raw_code = raw_code.strip()
        if len(raw_code) == 6 and raw_code.isdigit():
            if raw_code.startswith("6"):
                return f"sh{raw_code}"
            elif raw_code.startswith(("0", "3")):
                return f"sz{raw_code}"
            elif raw_code.startswith(("4", "8")):
                return f"bj{raw_code}"
        return raw_code

    def _infer_market(self, code: str) -> str:
        if code.startswith("6"):
            return "CN_SH"
        elif code.startswith(("0", "3")):
            return "CN_SZ"
        elif code.startswith(("4", "8")):
            return "CN_BJ"
        return "CN_SH"

    def probe_schema(self, rows: list) -> bool:
        if not rows:
            return False
        return isinstance(rows[0], dict) and len(rows[0]) > 0
