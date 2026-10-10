# Z8 Checkpoint — lovetrade 全量迁移

> 铸码执行 · 2026-10-10（周六）→ 10-12（周一）20:00 截止
> 来源：督军 Z8 波 · 梁总 10-10 晚四问裁决

## 裁决记录

| # | 问题 | 裁决 |
|---|------|------|
| 1 | 功能迁成可用 | 全量迁移，保证功能对等 |
| 2 | 板块降采样 | 批准（plate_movement_intraday 5min→新表） |
| 3 | LLM 通道 | DashScope Generation 直连（主） |
| 4 | Web 改接口 | 方案另波，Z8 不做 |

## 执行计划

| 波 | 内容 | 状态 |
|----|------|------|
| 前置 | 周一 09:00 龙虎实盘重测（Z7 待办） | ⏳ 待周一开盘 |
| W0 | 凭证安全化（明文口令→secrets.yaml） | ✅ |
| W1 | 数据补迁（D6题材4表+D12笔记2表+D10 report+meta 2表+catalyst delta） | ✅ |
| W2 | API 补全（catalyst/topic/market/note/report/calendar/home/auth） | ✅ |
| W2b | 定时任务迁移（6 个 scheduler） | ✅ |
| LLM | DashScope 直连 + Dify 审计 | ✅ |

## 纪律

- 对账不平即停，写差异报告
- 凭证不进报告/commit
- OpenAPI 每次端点变更同步导出
- 同错 2 次即停

---

## W0 凭证安全化 ✅ 已完成

| 项 | 状态 |
|----|------|
| secrets.yaml 新增 lovetrade/dashscope/web/dify 段 | ✅ |
| migrate_lovetrade.py 改读 secrets（删除硬编码） | ✅ |
| commit | `39ebc7c` |

## W1 数据补迁 ✅ 已完成

### V005 Migration（10 张新表）

| 域 | 表 | 源行数 | 目标行数 | 状态 |
|----|----|--------|----------|------|
| D6 | topic | 253 | 253 | ✅ |
| D6 | topic_category | 2,998 | 2,998 | ✅ |
| D6 | topic_group | 180 | 180 | ✅ |
| D6 | topic_links | 2,189 | 2,189 | ✅ |
| D12 | note_category | 4 | 4 | ✅ |
| D12 | trading_note | 84 | 84 | ✅ |
| D10 | report | 12 | 12 | ✅ |
| meta | dynamic_category_config | 12 | 12 | ✅ |
| meta | trading_system_node | 25 | 25 | ✅ |
| D12 | catalyst delta (pred+cog+state) | 34 | 25 | ✅ |

### 增量明细（catalyst delta post 10-08）

| 表 | delta 行数 | 写入 |
|----|-----------|------|
| catalyst_predictions | 15 | 15 |
| catalyst_impacts | 9 | 9 |
| catalyst_system_states | 1 | 1 |
| catalyst_active_messages | 9 | logged only |

### 空表（源端 0 行，不迁移）

- daily_market_performance
- market_performance_data
- speculative_performance_data
- stock_market_data

### home_summary

- 1 行（trading_plan_note_id 引用），非独立数据表，已检查记录

### commit

- `fb79d72`

## W2 API 补全 ✅ 已完成

### lovetrade_routes.py（31 端点）

| 组 | 端点 | 数量 |
|----|------|------|
| catalyst | /data/catalyst/impacts, /predictions, /system-states, /active-messages, /accuracy, /dashboard | 9 |
| topic | /data/topic/tree, /graph, /intro/{id}, /category-stocks/{id} | 4 |
| market | /data/market/radars, /messages, /dynamic-news, /plate-movements, /interval-stats, /daily-metrics | 6 |
| note | /data/notes (GET/POST), /data/note-categories | 4 |
| report | /data/reports, /data/reports/{id}, /data/reports/{type}/send | 3 |
| calendar | /meta/calendar/is-trading-day, /trading-session, /month-trading-days | 3 |
| home | /data/home/summary | 1 |
| auth | /auth/login | 1 |

**OpenAPI 总路径**: 50（含原有 19 + 新增 31）

### commit

- `f9b9a49`

## W2b 定时任务迁移 ✅ 已完成

### 新增作业（6 个）

| 作业 | cron | 域 | 目标表 | 说明 |
|------|------|----|--------|------|
| j_topic_sync | 0 8 * * 1-5 | D6 | topic* | 题材增量同步+AI解释+飞书推送 |
| j_radar | */30 9-15 * * 1-5 | D8 | radar_event | 市场雷达（longhu适配器） |
| j_market_messages_hot | */15 9-15 * * 1-5 | D9 | market_messages | 核心热点消息 |
| j_market_messages_other | */8 * * * * | D9 | market_messages | 动态分类消息 |
| j_plate_intraday | */5 9-15 * * 1-5 | D6 | plate_movement_intraday | 板块5min降采样 |
| j_prediction_sync | 0 9,18 * * 1-5 | D12 | prediction | 预测状态同步 |

### commit

- `997c608`

## LLM 通道 ✅ 已审计

### 主通道：DashScope Generation 直连

| 配置项 | 值 |
|--------|-----|
| API Key | secrets.yaml → dashscope.api_key |
| URL | https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation |
| 默认模型 | qwen-long-latest |
| topic-relation | qwen-long-latest |
| topic-explain | qwen-plus-latest |
| Prompt 常量 | RELATION_SYSTEM, EXPLAIN_SYSTEM（已移植到 j_topic_sync.py） |

### 辅通道：Dify Workflow 审计

| 应用 | 用途 | 状态 |
|------|------|------|
| app-nBM5tTzpJOcZUKk6SkL0ynRy | 晚报生成 | **活跃**（ReportService.callAppForEveningReport） |
| app-dFF9Szp4Slow7NeUl3omlWUn | 早报生成（备选） | 已注释，不活跃 |

### DashScope Application（SDK 调用）

| App ID | 用途 | 状态 |
|--------|------|------|
| 9c467a25dd5f41b2912f977132c9855d | 新闻分类评分 | 活跃（MarketTrendsService） |
| c21f272ebf644f58bf1fc3c91703d62b | 早报生成 | 活跃（ReportService，Java 侧 scheduler 已禁用） |

### 结论

- **Dify 晚报 workflow 仍有活任务依赖**，不建议本波切换
- Java 侧 Report scheduler 已禁用（morning-report: false, evening-report: false）
- 建议：Python 侧先用 DashScope Generation 实现报告生成，Dify 作为备选保留
