# 作业 Handler 矩阵

> 注册 ≠ 实装。本文档区分"已注册"与"已实装"。

## 已实装（handler 文件存在 + 实跑验证通过）

| 作业名 | handler 文件 | 状态 | 计划时点 | 域 | 验证日期 |
|--------|-------------|------|---------|-----|---------|
| j_index_daily | dworker/jobs/j_index_daily.py | ✅ 已实装 | 15:10 | D1 | 2026-10-08 |
| j_stock_daily | dworker/jobs/j_stock_daily.py | ✅ 已实装 | 15:30 | D2 | 2026-10-08 |
| j_global_overnight | dworker/jobs/j_global_overnight.py | ✅ 已实装 | 07:30 | D7 | 2026-10-08 |
| j_bidding_list | dworker/jobs/j_bidding_list.py | ✅ 已实装 | 09:26 | D3 | 2026-10-08 |
| j_bidding_snap1 | dworker/jobs/j_bidding_snap1.py | ✅ 已实装 | 09:15 | D3 | 2026-10-08 |
| j_bidding_snap2 | dworker/jobs/j_bidding_snap2.py | ✅ 已实装 | 09:20 | D3 | 2026-10-08 |
| j_bidding_snap3 | dworker/jobs/j_bidding_snap3.py | ✅ 已实装 | 09:25 | D3 | 2026-10-08 |

## 已注册但未实装（handler 文件不存在）

| 作业名 | 状态 | 计划时点 | 域 | 备注 |
|--------|------|---------|-----|------|
| j_trade_cal | 待实装 | 0 0 1 1 * | D0 | 交易日历 |
| j_instrument_master | 待实装 | 0 8 * * * | aux | 证券主档 |
| j_global_asia | 待实装 | 0 16 * * 1-5 | D7 | 亚洲收盘 |
| j_global_minute_pre | 待实装（disabled） | */15 6-9 * * 1-5 | D7 | 盘前分钟 |
| j_index_minute | 待实装 | 0 16 * * 1-5 | D1 | 指数分钟K |
| j_etf_daily | 待实装 | 35 15 * * 1-5 | D2 | ETF日K |
| j_zt_pools | 待实装 | 15 15 * * 1-5 | D3 | 涨停池 |
| j_sentiment_calc | 待实装 | 40 15 * * 1-5 | D3 | 情绪汇总 |
| j_stock_minute | 待实装（disabled） | 45 15 * * 1-5 | D2 | 个股分钟K |
| j_verify_daily | 待实装 | 0 17 * * 1-5 | pipe | 双源复核 |
| j_backfill_daily | 待实装 | 0 7 * * 1-5 | pipe | 次日补采 |
| j_coverage_check | 待实装 | 15 7 * * 1-5 | pipe | 覆盖率检查 |
| j_heartbeat | ✅ 内置 | */15 * * * * | pipe | 心跳 |
| j_daily_report | 待实装 | 45 16 * * 1-5 | pipe | 采集日报 |
| j_margin_daily | 待实装 | 0 17 * * 1-5 | D4 | 融资融券 |
| j_fund_flow | 待实装 | 20 15 * * 1-5 | D4 | 资金流 |
| j_sector_daily | 待实装 | 25 15 * * 1-5 | D5 | 板块日K |
| j_announcements | 待实装 | 0 18 * * 1-5 | D6 | 公告 |
| j_corporate_actions | 待实装 | 0 9 * * 1-5 | D6 | 公司行动 |
| j_holder_num | 待实装 | 0 18 * * 1-5 | D8 | 股东人数 |
| j_block_trade | 待实装 | 30 17 * * 1-5 | D8 | 大宗交易 |
| j_valuation | 待实装 | 0 19 * * 1-5 | D9 | 估值 |
| j_macro_indicators | 待实装 | 0 8 1,15 * * | D8 | 宏观指标 |

## 统计

- 已注册：32 个作业（含心跳）
- 已实装：7 个（j_index_daily, j_stock_daily, j_global_overnight, j_bidding_list + 3 snap）
- 待实装：24 个
- 实装率：22%

## 映射规则

handler 文件路径 = `dworker/jobs/{job_name}.py`
每个 handler 必须实现 `run(job_ctx, deg_chain, source_chain, conn, ingest_logger, raw_archiver, trigger)` 函数。
