# Z4c 采集实装热修 Checkpoint

## 开始时间：2026-10-08 09:42

## P0-A｜dsched 真调度
- [ ] APScheduler BlockingScheduler 实装
- [ ] compose 补 ../db 挂载
- [ ] 容器重建 + seed_jobs.yaml 可读验证
- [ ] ingest_log 出现 trigger='scheduled' 行

## P0-B｜4 个关键 handler
- [ ] j_bidding_list
- [ ] j_index_daily（含 sz399001）
- [ ] j_stock_daily
- [ ] j_global_overnight（21 品种）

## P0-C｜17:30 收盘首跑
- [ ] j_index_daily + j_stock_daily 实跑
- [ ] 回报行数 + ingest_log + data-api 实测

## P0-D｜明日 09:00 前
- [ ] bidding smoke test
- [ ] 09:15/09:20/09:25 三时点实盘

## P1
- [ ] job_handler_matrix.md
- [ ] backfill_stock_daily.py
- [ ] credentials.md


---
## 🔴 督军插入 09:45（务必先读 repo 根目录 URGENT_FROM_DUJUN.md）
trade_cal=0 / session_def=0 / instrument_master=1 / stock_daily=0 全表空 —— P0-B 必须先实装 j_trade_cal + j_instrument_master（走 akshare，已被墨测验证 50/50 PASS）；且任何跳过都必须写 ingest_log MISS/SKIP 行，禁止静默 return。tencent 源我已实测可用（20261008093851 实时行情），"外部无 2026 数据"结论作废。
---
