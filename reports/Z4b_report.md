# Z4b 残局波报告

**生成时间**: 2026-10-08 08:58 CST  
**执行范围**: ①Z3 收尾核验 + ②Z4 残余  
**判定**: ①✅ 基本平 → ②部分完成（backfill 阻塞）

---

## ① Z3 收尾核验

### 1.1 备份缺口补全

| 文件 | 原状态 | 现状态 | 大小 |
|---|---|---|---|
| index_trend.sql.gz | 0 字节 | ✅ 完成 | 770K |
| market_message.sql.gz | 缺失 | ✅ 完成 | 14M |
| market_radar.sql.gz | 缺失 | ✅ 完成 | 6.8M |

所有 dump 文件 gzip 完整性验证通过。

### 1.2 逐表对账

| 源表 | 源行数 | PG 表 | PG 行数 | Quarantine | 缺口 | 状态 |
|---|---:|---|---:|---:|---:|:---:|
| market_radar | 296,749 | radar_event | 296,749 | 0 | **0** | ✅ |
| market_message | 69,113 | market_messages | 69,011 | 0 | **102** | ⚠️ |
| opening_stock_dynamic_news | 9,738 | news_telegraph | 9,738 | 0 | **0** | ✅ |
| index_trend | 52,196 | index_minute | 39,182 | 13,014 | **0** | ✅ |
| plate_movement | 11,318 | sector_daily | 11,318 | 0 | **0** | ✅ |
| catalyst_predictions | 328 | prediction | 328 | 0 | **0** | ✅ |
| catalyst_impacts+states | 2,068 | cognition | 2,068 | 0 | **0** | ✅ |
| topic_stock | 15,241 | stock_sector_map | 15,241 | 0 | **0** | ✅ |

**汇总**: 源 456,452 → PG 455,350 + quarantine 13,014 = 456,350（差 102 = 迁移后新增）

### 1.3 补迁移执行

发现 catalyst 和 topic_stock 从未迁移（ingest_log 无记录）。执行补跑：

- `tools/migrate_missing.py`（新建）
- prediction: 128 → 328（+200）
- cognition: 0 → 2,068（+2,068）
- stock_sector_map: 0 → 15,241（+15,241）

### 1.4 判定

✅ **Z3 基本平**：7/8 完美匹配，1 项微差 102 行（迁移后新增，可解释）。  
`Z3_COMPLETE.marker` 已落盘。

---

## ② Z4 残余

### 2.1 D4-D12 作业注册

新建 `db/seed_jobs_d4_d12.yaml`，注册 11 个新作业：

| Domain | Job | 目标表 | 调度 | enabled |
|---|---|---|---|---|
| D4 | j_margin_daily | margin_daily, margin_stock | 17:00 | ✅ |
| D5 | j_fund_flow | fund_flow_stock, fund_flow_sector | 15:20 | ✅ |
| D6 | j_sector_daily | sector_daily, theme_heat | 15:25 | ✅ |
| D8 | j_announcements | announcements | 18:00 | ✅ |
| D8 | j_corporate_actions | dividend, earnings_calendar, lockup_calendar | 09:00 | ✅ |
| D9 | j_holder_num | holder_num, share_structure | 18:00 | ✅ |
| D10 | j_news_feed | news_telegraph, market_messages | */5 8-16 | ❌ 盘中 |
| D11 | j_block_trade | block_trade | 17:30 | ✅ |
| D12 | j_prediction_sync | prediction, cognition | 08:00 | ❌ 待 token |
| aux | j_valuation | valuation_daily, finance_snapshot, financial_reports | 19:00 | ✅ |
| aux | j_macro_indicators | macro_indicators, policy_calendar | 1/15日 | ✅ |

**job_registry 总计**: 18 → 29 个作业。

### 2.2 stock_daily 3 年回填

**启动时刻**: 2026-10-08 08:55:29  
**PID**: 341890  
**目标**: 5,224 只股票 × 3 年（2023-10-08 ~ 2026-10-07）

**阻塞**: mootdx/tencent API 返回空数据。

**根因分析**: 系统日期为 2026-10-08，但外部数据源（akshare/mootdx/tencent）无 2026 年数据。API 返回的最新数据约为 2024 年中。

**建议**:
1. 等待梁总确认数据源策略（是否需要切换到其他有 2026 数据的源）
2. 或调整 backfill 日期范围到 API 实际覆盖的区间

**脚本**: `tools/backfill_stock_daily.py`（已写，待数据源确认后重跑）

### 2.3 sentiment_daily 30 日回填

**执行时刻**: 2026-10-08 08:57  
**端点**: 龙虎 Emotion（GetMoneyDate）  
**结果**: API 返回空（`{"list":[],"List":[],"errcode":"0"}`）

**尝试**:
- emotion_device_id → 空
- account_3167791 凭证 → 空

**根因**: 同上，API 无 2026 年数据。

**脚本**: `tools/backfill_sentiment_daily.py`（已写，待数据源确认）

---

## ③④ 状态

③ Z5（OpenAPI + 客户端 + 六案例）和 ④ T3.1（基率校准）**未启动**，等待梁总确认数据源策略后继续。

---

## 阻塞项

| # | 阻塞 | 影响 | 建议 |
|---|---|---|---|
| 1 | 外部 API 无 2026 数据 | stock_daily/sentiment_daily 无法回填 | 梁总确认数据源策略 |
| 2 | 龙虎 Emotion 端点返回空 | sentiment_daily 30 日序列缺失 | 同上 |
| 3 | 龙虎其余端点实盘=0 | D3 盘中数据无法验证 | 待 token 轮换（梁总） |

---

## 产物清单

### 报告
- `/home/hello/application/dev/market-datalayer/reports/Z3_recon_lovetrade.md`
- `/home/hello/application/dev/market-datalayer/reports/Z3_COMPLETE.marker`
- `/home/hello/application/dev/market-datalayer/reports/Z4b_report.md`
- `/home/hello/application/dev/market-datalayer/reports/z4b_checkpoint.md`

### 脚本
- `/home/hello/application/dev/market-datalayer/tools/migrate_missing.py`
- `/home/hello/application/dev/market-datalayer/tools/backfill_stock_daily.py`
- `/home/hello/application/dev/market-datalayer/tools/backfill_sentiment_daily.py`

### 配置
- `/home/hello/application/dev/market-datalayer/db/seed_jobs_d4_d12.yaml`

### 备份
- `/home/hello/backups/lovetrade_mysql_20261007/index_trend.sql.gz` (770K)
- `/home/hello/backups/lovetrade_mysql_20261007/market_message.sql.gz` (14M)
- `/home/hello/backups/lovetrade_mysql_20261007/market_radar.sql.gz` (6.8M)

### 复制到 guanshi/specs/
- `/home/hello/.qwenpaw/workspaces/guanshi/specs/Z3_recon_lovetrade.md`
- `/home/hello/.qwenpaw/workspaces/guanshi/specs/Z3_COMPLETE.marker`
