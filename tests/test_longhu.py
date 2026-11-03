"""
tests/test_longhu.py
龙虎 adapter 单测：失效三分判定（网络/认证/恒空）+ 熔断机制
不打真实接口，全部 mock。
"""
import pytest
import time
from unittest.mock import patch, MagicMock

from dworker.adapters.longhu import LonghuAdapter, ENDPOINT_MAP
from dworker.core.degradation import (
    JobContext, SourceError, SourceErrorKind
)


class MockResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json = json_data or {}

    def json(self):
        return self._json


class TestLonghuThreeWayFailure:
    """失效三分判定测试。"""

    def setup_method(self):
        self.adapter = LonghuAdapter()
        self.job_ctx = JobContext(
            job_name="test_longhu",
            domain="D3",
            target_tables=["zt_pool"]
        )

    @patch.object(LonghuAdapter, '_load_secrets')
    def test_network_failure(self, mock_secrets):
        """网络超时 → SourceErrorKind.NETWORK。"""
        mock_secrets.return_value = {
            "hosts": {"apphwhq": "https://apphwhq.longhuvip.com/w1/api/index.php"},
            "longhu_secondary": {"device_id": "test_device"},
        }
        adapter = LonghuAdapter()

        with patch.object(adapter.session, 'post', side_effect=Exception("Connection timeout")):
            with pytest.raises(SourceError) as exc_info:
                adapter.fetch(self.job_ctx, {"endpoint": "Radar"})
            assert exc_info.value.kind == SourceErrorKind.NETWORK

    @patch.object(LonghuAdapter, '_load_secrets')
    def test_auth_failure(self, mock_secrets):
        """认证失败 (errcode=-1) → SourceErrorKind.AUTH。"""
        mock_secrets.return_value = {
            "hosts": {"apphwhq": "https://apphwhq.longhuvip.com/w1/api/index.php"},
            "longhu_secondary": {"device_id": "test_device"},
        }
        adapter = LonghuAdapter()

        mock_resp = MockResponse(200, {"errcode": "-1", "errmsg": "token expired"})
        with patch.object(adapter.session, 'post', return_value=mock_resp):
            with pytest.raises(SourceError) as exc_info:
                adapter.fetch(self.job_ctx, {"endpoint": "Radar"})
            assert exc_info.value.kind == SourceErrorKind.AUTH

    @patch.object(LonghuAdapter, '_load_secrets')
    def test_empty_response(self, mock_secrets):
        """恒空 (errcode=0 + 空数据) → SourceErrorKind.EMPTY。"""
        mock_secrets.return_value = {
            "hosts": {"apphwhq": "https://apphwhq.longhuvip.com/w1/api/index.php"},
            "longhu_secondary": {"device_id": "test_device"},
        }
        adapter = LonghuAdapter()

        # errcode=0 but empty data
        mock_resp = MockResponse(200, {"errcode": "0", "list": [], "data": []})
        with patch.object(adapter.session, 'post', return_value=mock_resp):
            with pytest.raises(SourceError) as exc_info:
                adapter.fetch(self.job_ctx, {"endpoint": "Radar"})
            assert exc_info.value.kind == SourceErrorKind.EMPTY

    @patch.object(LonghuAdapter, '_load_secrets')
    def test_rate_limit_circuit_breaker(self, mock_secrets):
        """HTTP 429 → 触发熔断 → SourceErrorKind.RATE_LIMIT。"""
        mock_secrets.return_value = {
            "hosts": {"apphwhq": "https://apphwhq.longhuvip.com/w1/api/index.php"},
            "longhu_secondary": {"device_id": "test_device"},
        }
        adapter = LonghuAdapter()

        mock_resp = MockResponse(429, {})
        with patch.object(adapter.session, 'post', return_value=mock_resp):
            with pytest.raises(SourceError) as exc_info:
                adapter.fetch(self.job_ctx, {"endpoint": "Radar"})
            assert exc_info.value.kind == SourceErrorKind.RATE_LIMIT

        # 后续调用应被熔断
        with pytest.raises(SourceError) as exc_info:
            adapter.fetch(self.job_ctx, {"endpoint": "Radar"})
        assert exc_info.value.kind == SourceErrorKind.RATE_LIMIT
        assert "Circuit breaker" in str(exc_info.value)

    @patch.object(LonghuAdapter, '_load_secrets')
    def test_emotion_parse(self, mock_secrets):
        """Emotion 端点解析：CGL/YLL 30日序列。"""
        mock_secrets.return_value = {
            "hosts": {"apphis": "https://apphis.longhuvip.com/w1/api/index.php"},
            "emotion_device_id": "test_device",
        }
        adapter = LonghuAdapter()

        mock_resp = MockResponse(200, {
            "errcode": "0",
            "ZY": [
                {"Day": "2026-09-30", "CGL": 52.94, "YLL": 1.21},
                {"Day": "2026-09-29", "CGL": 48.5, "YLL": -0.5},
            ]
        })
        with patch.object(adapter.session, 'post', return_value=mock_resp):
            result = adapter.fetch(self.job_ctx, {"endpoint": "Emotion"})
            assert len(result.rows) == 2
            assert result.rows[0]["dbcgl"] == 52.94
            assert result.rows[0]["dbyll"] == 1.21

    @patch.object(LonghuAdapter, '_load_secrets')
    def test_popularity_parse(self, mock_secrets):
        """PopularityList 端点解析：代码序列。"""
        mock_secrets.return_value = {
            "hosts": {"apphwshhq": "https://apphwshhq.longhuvip.com/w1/api/index.php"},
            "longhu_primary": {"user_id": "user", "token": "test", "device_id": "test"},
        }
        adapter = LonghuAdapter()

        mock_resp = MockResponse(200, {
            "errcode": "0",
            "List": ["000678", "603259", "600825"]
        })
        with patch.object(adapter.session, 'post', return_value=mock_resp):
            result = adapter.fetch(self.job_ctx, {"endpoint": "PopularityList"})
            assert len(result.rows) == 3
            assert result.rows[0]["code"] == "000678"
            assert result.rows[0]["rank"] == 1

    def test_endpoint_map_completeness(self):
        """验证 ENDPOINT_MAP 覆盖 D3 关键 4 端点。"""
        required = ["DailyLimitResumption", "Emotion", "Radar", "MorningBiddingList"]
        for ep in required:
            assert ep in ENDPOINT_MAP, f"Missing endpoint: {ep}"

    @patch.object(LonghuAdapter, '_load_secrets')
    def test_call_count_tracking(self, mock_secrets):
        """调用计数追踪。"""
        mock_secrets.return_value = {
            "hosts": {"apphis": "https://apphis.longhuvip.com/w1/api/index.php"},
            "emotion_device_id": "test_device",
        }
        adapter = LonghuAdapter()
        assert adapter.call_count == 0

        mock_resp = MockResponse(200, {"errcode": "0", "ZY": [{"Day": "2026-09-30", "CGL": 50, "YLL": 1}]})
        with patch.object(adapter.session, 'post', return_value=mock_resp):
            adapter.fetch(self.job_ctx, {"endpoint": "Emotion"})
            assert adapter.call_count == 1
            adapter.fetch(self.job_ctx, {"endpoint": "Emotion"})
            assert adapter.call_count == 2
