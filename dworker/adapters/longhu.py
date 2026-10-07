"""
龙虎 longhuvip 适配器
5 主机 + 双账号凭证外置 + UA池 + 0.5rps burst1 + 失效三分判定
§11.7 T-R1 / §11.8

凭证来源：lovetrade-service Java 代码提取，外置到 configs/secrets.yaml
token 轮换 gate 待梁总供应商侧操作 → 本波配置化占位，轮换后仅改 secrets.yaml
"""
import logging
import random
import time
from typing import Optional

import requests
import yaml
from pathlib import Path

from .base import BaseAdapter
from dworker.core.degradation import (
    JobContext, FetchResult, SourceError, SourceErrorKind
)

logger = logging.getLogger(__name__)

SECRETS_PATH = Path(__file__).resolve().parent.parent.parent / "configs" / "secrets.yaml"

# UA 池（参照 Java 代码中的 UA 格式）
UA_POOL = [
    "Dalvik/2.1.0 (Linux; U; Android 12; OCE-AN50 Build/HUAWEIOCE-AN50)",
    "Mozilla/5.0 (Linux; Android 12; OCE-AN50 Build/HUAWEIOCE-AN50; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/114.0.5735.196 Mobile Safari/537.36;kaipanla 5.19.0.0",
    "Dalvik/2.1.0 (Linux; U; Android 13; SM-G9810 Build/TP1A.220624.014)",
    "Mozilla/5.0 (Linux; Android 13; SM-G9810 Build/TP1A.220624.014; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/114.0.5735.196 Mobile Safari/537.36;kaipanla 5.21.0.0",
]

# 端点 → 主机/账号映射
ENDPOINT_MAP = {
    # D3 涨停复牌/板块 → apphwhq, DeviceID 认证
    "DailyLimitResumption": {
        "host": "apphwhq",
        "a": "DailyLimitResumption",
        "c": "GetPlateInfo_w38",
        "auth": "device_3167791",
    },
    # D3 情绪 → apphis, 无账号认证
    "Emotion": {
        "host": "apphis",
        "a": "GetMoneyDate",
        "c": "Emotion",
        "auth": "emotion_device",
    },
    # D3 市场雷达 → apphwhq, DeviceID 认证
    "Radar": {
        "host": "apphwhq",
        "a": "Radar",
        "c": "HomeDingPan",
        "auth": "device_3167791",
    },
    # D3 竞价列表 → apphwhq, 专用凭证
    "MorningBiddingList": {
        "host": "apphwhq",
        "a": "MorningBiddingList",
        "c": "HomeDingPan",
        "auth": "entrust_purchase",
    },
    # D3 龙头异动 → apphwhq, DeviceID 认证
    "DragonHeadStock": {
        "host": "apphwhq",
        "a": "HomeDingPan",
        "c": "HomeDingPan",
        "auth": "device_3167791",
    },
    # D3 市场表现多视图 → apphwhq, 账号 3167791
    "MarketPerformance": {
        "host": "apphwhq",
        "a": "GetInfo",
        "c": "Index",
        "auth": "account_3167791",
    },
    # D4 游资动向 → applhb, 账号 3965820
    "YouZiDongXiang": {
        "host": "applhb",
        "a": "YouZiDongXiangByList",
        "c": "Index",
        "auth": "account_3965820",
    },
    # D6 人气榜 → apphwshhq, 账号 3965820
    "PopularityList": {
        "host": "apphwshhq",
        "a": "GetRQZ_Data",
        "c": "Index",
        "auth": "account_3965820",
    },
    # D6 板块排名 → apphwhq, DeviceID 认证
    "PlateMovement": {
        "host": "apphwhq",
        "a": "RealRankingInfo",
        "c": "ZhiShuRanking",
        "auth": "device_plate",
    },
    # D6 风车 → apphwhq, 账号 3965820
    "MarketWind": {
        "host": "apphwhq",
        "a": "GetFengKList",
        "c": "StockFengKData",
        "auth": "account_3965820",
    },
    # D6 最强风车 → apphwshhq, 账号 3965820
    "StrongestWind": {
        "host": "apphwshhq",
        "a": "GetFengKListBest",
        "c": "StockFengKData",
        "auth": "account_3965820",
    },
    # D6 指数成分股 → apphwshhq, 账号 3965820
    "WindVane": {
        "host": "apphwshhq",
        "a": "ZhiShuStockList_W8",
        "c": "ZhiShuRanking",
        "auth": "account_3965820",
    },
    # D6 题材信息 → applhb, 账号 3167791 + 专用 token
    "ThemeInfo": {
        "host": "applhb",
        "a": "InfoGet",
        "c": "Theme",
        "auth": "theme_info",
    },
    # D1 指数 L2 → apphwhq, DeviceID 认证
    "IndexTrend": {
        "host": "apphwhq",
        "a": "GetZsTrend",
        "c": "StockL2Data",
        "auth": "device_3167791",
    },
    # D2 个股 L2 → apphwshhq, DeviceID 认证
    "StockDetail": {
        "host": "apphwshhq",
        "a": "GetStockPanKou_Narrow",
        "c": "StockL2Data",
        "auth": "device_3965820",
    },
    # D10 直播/概念点 → apphwhq, DeviceID 认证
    "OpeningStockDynamicNews": {
        "host": "apphwhq",
        "a": "ZhiBoContent",
        "c": "ConceptionPoint",
        "auth": "device_3167791",
    },
    # D6 概念查询 → apparticle, 账号 3965820
    "StockConcept": {
        "host": "apparticle",
        "a": "GetConceptJXBKw23",
        "c": "StockF10Basic",
        "auth": "account_3965820",
    },
    # D3 涨停表现 → apphwhq, DeviceID 认证
    "DailyLimitPerformance": {
        "host": "apphwhq",
        "a": "HomeDingPan",
        "c": "HomeDingPan",
        "auth": "device_3167791",
    },
}


class LonghuAdapter(BaseAdapter):
    """
    龙虎 longhuvip 适配器。
    5 主机 + 双账号 + UA池 + 0.5rps burst1 + 失效三分判定。
    """
    source_name = "longhu"

    def __init__(self, secrets_path: str = None, timeout: int = 10):
        self.timeout = timeout
        self.session = requests.Session()
        self._secrets = self._load_secrets(secrets_path)
        self._call_count = 0  # 配额追踪
        self._circuit_breaker_until = 0  # 熔断时间戳

    def _load_secrets(self, path: str = None) -> dict:
        p = Path(path) if path else SECRETS_PATH
        if not p.exists():
            logger.warning(f"secrets.yaml not found at {p}, using empty config")
            return {}
        with open(p) as f:
            cfg = yaml.safe_load(f) or {}
        return cfg.get("longhu", {})

    def _get_host_url(self, host_key: str) -> str:
        hosts = self._secrets.get("hosts", {})
        return hosts.get(host_key, f"https://{host_key}.longhuvip.com/w1/api/index.php")

    def _get_auth_params(self, auth_type: str) -> dict:
        """根据认证类型返回对应凭证参数。"""
        if auth_type == "account_3965820":
            acct = self._secrets.get("account_3965820", {})
            return {
                "UserID": acct.get("user_id", "3965820"),
                "Token": acct.get("token", ""),
                "DeviceID": acct.get("device_id", ""),
            }
        elif auth_type == "account_3167791":
            acct = self._secrets.get("account_3167791", {})
            return {
                "UserID": acct.get("user_id", "3167791"),
                "Token": acct.get("token", ""),
                "DeviceID": acct.get("device_id", ""),
            }
        elif auth_type == "device_3167791":
            acct = self._secrets.get("account_3167791", {})
            return {"DeviceID": acct.get("device_id", "")}
        elif auth_type == "device_3965820":
            acct = self._secrets.get("account_3965820", {})
            return {"DeviceID": acct.get("device_id", "")}
        elif auth_type == "device_plate":
            # PlateMovement 用 64hex DeviceID
            return {"DeviceID": "07ba97d5a3259b5130a2cb0f3042e39573a7a5427d9eb138120f8ce65a56125e"}
        elif auth_type == "emotion_device":
            return {"DeviceID": self._secrets.get("emotion_device_id", "")}
        elif auth_type == "entrust_purchase":
            ep = self._secrets.get("entrust_purchase", {})
            return {
                "UserID": ep.get("user_id", ""),
                "Token": ep.get("token", ""),
                "DeviceID": ep.get("device_id", ""),
            }
        elif auth_type == "theme_info":
            acct = self._secrets.get("account_3167791", {})
            return {
                "UserID": acct.get("user_id", "3167791"),
                "Token": self._secrets.get("theme_info_token", ""),
                "DeviceID": acct.get("device_id", ""),
            }
        return {}

    def _check_circuit_breaker(self):
        """检查熔断状态。"""
        if time.time() < self._circuit_breaker_until:
            raise SourceError(
                SourceErrorKind.RATE_LIMIT,
                f"Circuit breaker active until {self._circuit_breaker_until}",
                self.source_name
            )

    def _trigger_circuit_breaker(self, duration_s: int = 1800):
        """触发熔断（30min 默认）。"""
        self._circuit_breaker_until = time.time() + duration_s
        logger.error(f"🔴 龙虎全源熔断 {duration_s}s，切备源")

    def fetch(self, job_ctx: JobContext, params: dict) -> FetchResult:
        """
        龙虎端点调用。
        params: {endpoint: str, extra_params: dict}
        """
        endpoint = params.get("endpoint", "")
        extra_params = params.get("extra_params", {})

        if endpoint not in ENDPOINT_MAP:
            raise SourceError(
                SourceErrorKind.SCHEMA_CHANGE,
                f"Unknown endpoint: {endpoint}",
                self.source_name
            )

        self._check_circuit_breaker()

        ep_config = ENDPOINT_MAP[endpoint]
        host_url = self._get_host_url(ep_config["host"])
        auth_params = self._get_auth_params(ep_config["auth"])

        # 构造请求参数
        req_params = {
            "a": ep_config["a"],
            "c": ep_config["c"],
            "PhoneOSNew": "1",
            "VerSion": "5.21.0.0",
            "apiv": "w42",
        }
        req_params.update(auth_params)
        req_params.update(extra_params)

        # UA 随机选择
        ua = random.choice(UA_POOL)
        headers = {
            "User-Agent": ua,
            "Host": ep_config["host"] + ".longhuvip.com",
            "Connection": "Keep-Alive",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }

        try:
            resp = self.session.post(
                host_url,
                data=req_params,
                headers=headers,
                timeout=self.timeout
            )
            self._call_count += 1

            if resp.status_code == 429 or resp.status_code == 403:
                self._trigger_circuit_breaker()
                raise SourceError(
                    SourceErrorKind.RATE_LIMIT,
                    f"HTTP {resp.status_code} - circuit breaker triggered",
                    self.source_name
                )

            if resp.status_code != 200:
                raise SourceError(
                    SourceErrorKind.NETWORK,
                    f"HTTP {resp.status_code}",
                    self.source_name
                )

            data = resp.json()

            # 失效三分判定
            errcode = data.get("errcode", "")
            if str(errcode) not in ("0", ""):
                # 认证失败
                if str(errcode) in ("-1", "-2", "1001", "1002"):
                    raise SourceError(
                        SourceErrorKind.AUTH,
                        f"Auth failed: errcode={errcode}, msg={data.get('errmsg', '')}",
                        self.source_name
                    )
                raise SourceError(
                    SourceErrorKind.NETWORK,
                    f"API error: errcode={errcode}, msg={data.get('errmsg', '')}",
                    self.source_name
                )

            # 恒空判定
            rows = self._parse_response(endpoint, data)
            if not rows:
                raise SourceError(
                    SourceErrorKind.EMPTY,
                    f"Empty response for endpoint={endpoint}",
                    self.source_name
                )

            return FetchResult(
                source=self.source_name,
                rows=rows,
                raw_payload=data
            )

        except requests.exceptions.Timeout:
            raise SourceError(SourceErrorKind.NETWORK, "Request timeout", self.source_name)
        except requests.exceptions.ConnectionError:
            raise SourceError(SourceErrorKind.NETWORK, "Connection failed", self.source_name)
        except SourceError:
            raise
        except Exception as e:
            raise SourceError(SourceErrorKind.NETWORK, str(e), self.source_name)

    def _parse_response(self, endpoint: str, data: dict) -> list:
        """解析端点响应为行列表。"""
        if endpoint == "Emotion":
            return self._parse_emotion(data)
        elif endpoint == "DailyLimitResumption":
            return self._parse_daily_limit(data)
        elif endpoint == "Radar":
            return self._parse_radar(data)
        elif endpoint == "MorningBiddingList":
            return self._parse_bidding(data)
        elif endpoint == "PopularityList":
            return self._parse_popularity(data)
        elif endpoint == "MarketPerformance":
            return self._parse_market_perf(data)
        elif endpoint == "PlateMovement":
            return self._parse_plate_movement(data)
        else:
            # 通用解析：返回原始 data 作为单行
            return [data] if data else []

    def _parse_emotion(self, data: dict) -> list:
        """解析 Emotion 端点：CGL/YLL 30日序列。"""
        zy_list = data.get("ZY", [])
        rows = []
        for item in zy_list:
            rows.append({
                "date": item.get("Day", ""),
                "dbcgl": float(item.get("CGL", 0)) if item.get("CGL") else None,
                "dbyll": float(item.get("YLL", 0)) if item.get("YLL") else None,
            })
        return rows

    def _parse_daily_limit(self, data: dict) -> list:
        """解析 DailyLimitResumption：nums六项 + list 19列数组。"""
        rows = []
        # nums 六项 → sentiment_daily 级别汇总
        nums = data.get("nums", {})
        if nums:
            rows.append({
                "type": "sentiment_summary",
                "up_cnt": int(nums.get("SZJS", 0)),
                "down_cnt": int(nums.get("XDJS", 0)),
                "limit_up": int(nums.get("ZT", 0)),
                "limit_down": int(nums.get("DT", 0)),
                "broken_rate": float(nums.get("ZBL", 0)),
                "yest_rase": float(nums.get("yestRase", 0)),
            })

        # list 涨停明细
        list_data = data.get("list", [])
        for group in list_data:
            stocks = group.get("StockList", [])
            for stock in stocks:
                if isinstance(stock, list) and len(stock) >= 19:
                    rows.append({
                        "type": "zt_stock",
                        "code": stock[0],
                        "name": stock[1],
                        "close": float(stock[2]) if stock[2] else None,
                        "pct": float(stock[3]) if stock[3] else None,
                        "amount": float(stock[4]) if stock[4] else None,
                        "circ_mv": float(stock[5]) if stock[5] else None,
                        "turnover_rate": float(stock[6]) if stock[6] else None,
                        "seal_amount": float(stock[7]) if stock[7] else None,
                        "first_seal_time": stock[8],
                        "last_seal_time": stock[9],
                        "break_times": int(stock[10]) if stock[10] else None,
                        "up_days": int(stock[11]) if stock[11] else None,
                        "board_days": int(stock[12]) if stock[12] else None,
                        "industry": stock[13],
                        "theme": stock[16] if len(stock) > 16 else None,
                        "reason": stock[17] if len(stock) > 17 else None,
                    })
        return rows

    def _parse_radar(self, data: dict) -> list:
        """解析 Radar 端点。"""
        items = data.get("list", data.get("data", []))
        rows = []
        for item in items:
            if isinstance(item, dict):
                rows.append(item)
        return rows

    def _parse_bidding(self, data: dict) -> list:
        """解析 MorningBiddingList 端点。"""
        items = data.get("list", data.get("data", []))
        rows = []
        for item in items:
            if isinstance(item, dict):
                rows.append({
                    "code": item.get("code", item.get("Code", "")),
                    "name": item.get("name", item.get("Name", "")),
                    "jjzf": float(item.get("jjzf", 0)) if item.get("jjzf") else None,
                    "jjje": int(item.get("jjje", 0)) if item.get("jjje") else None,
                    "jjcje": int(item.get("jjcje", 0)) if item.get("jjcje") else None,
                    "jjhs": float(item.get("jjhs", 0)) if item.get("jjhs") else None,
                    "ztwme": int(item.get("ztwme", 0)) if item.get("ztwme") else None,
                    "twenty_ztwme": int(item.get("twenty_ztwme", 0)) if item.get("twenty_ztwme") else None,
                    "fd": int(item.get("fd", 0)) if item.get("fd") else None,
                    "zdfd": int(item.get("zdfd", 0)) if item.get("zdfd") else None,
                    "sjlt": int(item.get("sjlt", 0)) if item.get("sjlt") else None,
                    "ssbk": item.get("ssbk"),
                    "ztsj": item.get("ztsj"),
                    "ztyy": item.get("ztyy"),
                    "bkztsl": int(item.get("bkztsl", 0)) if item.get("bkztsl") else None,
                    "limit_up_status": item.get("limit_up_status"),
                })
        return rows

    def _parse_popularity(self, data: dict) -> list:
        """解析 GetRQZ_Data：人气榜代码序列。"""
        items = data.get("List", [])
        rows = []
        for i, item in enumerate(items):
            if isinstance(item, dict):
                rows.append({
                    "code": item.get("code", item.get("Code", "")),
                    "name": item.get("name", ""),
                    "rank": i + 1,
                })
            elif isinstance(item, str):
                rows.append({"code": item, "rank": i + 1})
        return rows

    def _parse_market_perf(self, data: dict) -> list:
        """解析 GetInfo/Index 多视图。"""
        return [data] if data else []

    def _parse_plate_movement(self, data: dict) -> list:
        """解析 RealRankingInfo：板块排名 19列数组。"""
        items = data.get("list", [])
        rows = []
        for item in items:
            if isinstance(item, list) and len(item) >= 19:
                rows.append({
                    "code": item[0],
                    "name": item[1],
                    "stock_count": int(item[2]) if item[2] else None,
                    "pct": float(item[3]) if item[3] else None,
                    "strong": float(item[4]) if len(item) > 4 and item[4] else None,
                    "large_force": float(item[5]) if len(item) > 5 and item[5] else None,
                    "main_net": float(item[6]) if len(item) > 6 and item[6] else None,
                    "super_large_net": float(item[7]) if len(item) > 7 and item[7] else None,
                })
        return rows

    @property
    def call_count(self) -> int:
        return self._call_count

    def probe_schema(self, rows: list) -> bool:
        if not rows:
            return False
        return isinstance(rows, list) and len(rows) > 0
