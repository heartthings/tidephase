# 测试残留清理记录（D12 命名空间释放）· 2026-10-10 夜

> 执行：督军 ｜ 起因：观势 seeding F-001~F-010 被 Z7c 端点验证残留占用（POST /d12/cognition 返 409 CONFLICT）

## 清理前快照（逐行留档，可复核）
```
-- cognition:
{"cognition_id":"F-001","version":1,"type":"F","title":"测试认知","statement":"测试陈述","source":"test","confidence":0.8,"regime_scope":null,"validations":null,"falsifications":null,"derives_from":null,"status":"active","actor":"guanshi","created_at":"2026-10-10T19:46:18.101041+08:00","updated_at":"2026-10-10T19:46:18.101041+08:00","ingest_ts":"2026-10-10T19:46:18.101041+08:00"}
-- prediction:
{"prediction_id":"P-20261010-001","created_at":"2026-10-10T19:46:18.201774+08:00","statement":"测试预测","category":"情绪","confidence_pct":75,"base_rate_ref":null,"conditions":{"cognition_ids": ["F-001"]},"falsify":{"metric": "stock_daily.pct", "direction": "above", "threshold": 0.02},"check_date":"2026-10-13","regime_at_create":null,"result":"hit","result_note":"测试改判","checked_at":"2026-10-10T19:46:18.255411+08:00","writeback_done":false,"actor":"guanshi","source":"guanshi","ingest_ts":"2026-10-10T19:46:18.201774+08:00","horizon":"T1","reasoning_trace":null,"alternatives":null}
```

## 判定依据
- cognition F-001：title='测试认知'、source='test'、created_at=2026-10-10 19:46（=铸码 Z7c 写端点验证时刻），非观势真实认知
- prediction P-20261010-001：statement='测试预测'、created_at/checked_at 同为 19:46:18，非真实决策
- 两行均为端点验证残留；reflection 表 0 行，无下游引用；route_map 未引用

## 清理动作与结果
```
deleted cognition: F-001
DELETE 1
deleted prediction: P-20261010-001
DELETE 1
-- 复核（应全为 0）:
F-001 残留=0
P-20261010-001 残留=0
F-0xx 段占用数=0
cognition 总行数=2077
prediction 总行数=343
```

## 结论
- F-001~F-010 命名空间已释放，观势可立即 seeding（POST /d12/cognition，write token）
- 纪律留痕：删除前逐行 JSON 快照已存档本文件；非静默删除
