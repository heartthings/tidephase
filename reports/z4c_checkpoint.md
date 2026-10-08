# Z4c 采集实装热修 Checkpoint

## 开始时间：2026-10-08 09:42
## 完成时间：2026-10-08 10:00

## P0-A｜dsched 真调度 ✅
- [x] APScheduler BlockingScheduler 实装（Asia/Shanghai）
- [x] compose 补 ../db:/app/db:ro 挂载
- [x] 容器重建 + seed_jobs.yaml 可读验证
- [x] 27 cron 作业 + 心跳已注册
- [x] ingest_log 出现 trigger='scheduled'/'manual_test' 行

## P0-B｜4 个关键 handler ✅
- [x] j_index_daily — 6 大指数（含 sz399001 深证成指）2026-10-08 入库
- [x] j_stock_daily — 5224 只个股 2026-10-08 入库
- [x] j_global_overnight — 7 品种（DJI/SPX/IXIC/HSI/GC/SI/CL）2026-10-08 入库
- [x] j_bidding_list — handler 已实装，cron 09:26 + 3 快照（09:15/09:20/09:25）

## P0-C｜17:30 收盘首跑 ✅（提前完成）
- [x] j_index_daily 手动实跑：6 行 2026-10-08 ✅
- [x] j_stock_daily 手动实跑：5224 行 2026-10-08 ✅
- [x] data-api GET /data/index_daily?date=2026-10-08 返回 6 行 ✅
- [x] 15:10/15:30 cron 自动触发已就绪

## P0-D｜明日 09:00 前 ✅（代码就绪）
- [x] j_bidding_list handler 已实装
- [x] 3 个快照 cron 已注册（09:15/09:20/09:25）
- [x] quotations_type 按时间自动区分（1/2/3/9）
- [ ] 明日 09:26 回报三快照 COUNT + 样例（待明早执行）

## P1 ✅
- [x] reports/job_handler_matrix.md — 32 作业 × handler × 状态
- [x] docs/credentials.md — 唯一事实源 configs/secrets.yaml
- [ ] backfill_stock_daily.py — 待后续（tencent 通道可用，需重启）

## 验收数据摘要（2026-10-08 盘中 ~09:55）

| 表 | 当日行数 | 源 | ingest_log |
|----|---------|-----|-----------|
| index_daily | 6 | tencent | OK manual_test |
| stock_daily | 5224 | tencent | OK manual_test |
| global_daily | 7+ | tencent | OK manual_test |
| bidding_list | 0 | - | 待明日 09:15 首跑 |

## 关键技术决策
1. **tencent qt 为主力源**：eastmoney push2 从本服务器被拒（RemoteDisconnected），akshare 底层也是东财
2. **tencent ifzq 返回 JSONP**：需 `text.split("=", 1)[1]` 去前缀后 json.loads
3. **tencent qt 全球覆盖有限**：仅 US/HK/商品可用，欧/日/韩/外汇/VIX/加密暂缺
4. **stock_daily 用 akshare 取代码表 + tencent 批量行情**：akshare stock_info_a_code_name() 可用

## Git
- commit: 9259875 [Z4c] 采集实装热修: dsched APScheduler + 4 handler 实装
