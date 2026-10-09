# 督军 P0-A 审计（2026-10-08 12:05–12:15，只读实测）

## 判定：**PASS（有条件）** — 真调度机制实证落地，终验点 = 今日 15:10 j_index_daily 首次自然 cron 触发
（督军已建自动闸门 cron `71b81282` @15:12；若届时无 `🔔 CRON FIRED: j_index_daily` + ingest_log scheduled OK 行 → 改判 FAIL 并升级梁总+观势）

## 四项标准逐条证据

| # | 标准 | 结果 | 证据 |
|---|------|------|------|
| ① | sched 日志真实作业触发(非仅心跳) | **PASS(机制)/窗口内无业务到期** | 09:56:22 APScheduler 真启动，job_registry 驱动注册 20 业务作业+heartbeat（misfire_grace=3600, coalesce）；09:56–12:05 仅 heartbeat 派发（每15min 准点，executed successfully）。**排程事实**：seed cron 上午作业止于 09:26/09:45，下午自 15:10 起 → 窗口内 0 业务触发属物理不可能，非派发失败 |
| ② | ingest_log 有 scheduled 行 | **PASS(字面)/业务行待15:10** | scheduled 72 行（全为 j_heartbeat，09:56 起每 15min 一条 OK）；业务作业 scheduled 行 = 0（同①原因）。另有 **manual_test 6 行**：j_index_daily OK 6行×2、j_stock_daily FAIL(0)→OK 5224行、j_global_overnight OK 7/5行 |
| ③ | compose 补 ../db 挂载 | **PASS** | ops/docker-compose.yml market-sched volumes 含 `../db:/app/db:ro`；docker inspect 运行时确认 `/app/db` 已挂载 |
| ④ | dworker/jobs/ 文件数 | **8 个**（G2 时=0） | 实质 handler 4 个：j_bidding_list(7.7K)/j_global_overnight(8.6K)/j_index_daily(10.7K)/j_stock_daily(10.2K)；stub 3 个：j_bidding_snap1/2/3(112B，明日09:26三时点用)；__init__.py |

## 数据面落地交叉验证（12:10 psql 实测）
- stock_daily：今日 **5224 行**（此前全表 0）
- index_daily：今日 **6 行**（此前 MAX=09-30）
- global_daily：今日 **17 行**（此前 MAX=10-07）
- 链路结论：handler → runner.execute_job → PG → ingest_log **端到端已打通**（manual 路径实证）

## 事故记录（记名，不触发停止线）
- **R1 崩溃循环**：09:48:10–09:48:22 共 9 次启动，`AttributeError: 'Job' object has no attribute 'job_id'`（dsched/main.py:276，APScheduler Job 属性应为 `.id`）→ 09:48 修复、09:56:21 起稳定运行（healthy 2h+）。**铸码 bug 记名第 1 次**（doom 纪律：同类错误第 2 次即停线）。
- **G6 前置缺口仍开放**：trade_cal=0 / session_def=0 / instrument_master=1 / watchlist=1 / bidding_list=0。注：j_stock_daily 在 trade_cal=0 下手动跑通 → 未硬阻塞采集；但 **j_trade_cal cron="0 0 1 1 *"（每年1/1）→ 无自然回填点**，观势验证引擎若需交易日判定，需要铸码做一次 manual seed/backfill。

## 追问铸码（非阻塞，P0-B 间隙答复即可，task-4e37e670bb73）
1. **R2**：j_stock_daily manual 首跑 09:50:36 FAIL(0行) 的根因？（09:53 重试 OK 5224 行）——请补进 z4c_checkpoint.md，避免同坑二踩。
2. **R3 幂等性**：09:53 写入的 5224 行 date=2026-10-08 是**盘中快照**。15:30 j_stock_daily 收盘跑必须覆盖更新（upsert by (symbol,date)？还是 append？）——若是 append 会产生重复行污染今晚 P0-C 的 PG vs data-api 交叉核对。**请 15:00 前确认并在 checkpoint 注明**。
3. **R4 口径**：13 个已注册但无 handler 的作业（j_zt_pools 15:15 / j_etf_daily 15:35 / j_sentiment_calc 15:40 / j_stock_minute 15:45 / j_global_asia 16:00 / j_daily_report 16:45 / j_verify_daily 17:00 等）触发时将写 `note="handler not implemented"` MISS 行——runner.py 防静默跳过设计，**属预期**。今晚 17:50 P0-C 核查时督军按此口径区分「预期 MISS」与「真事故」，如口径有变请立即更新 checkpoint。
4. **R5**：compose market-worker command 仍是占位符（`print('market-worker ready...')`+sleep），实际执行模型为 sched 容器内 in-process 直跑。当前可接受，但请在 Z4c 收口报告中明确记载执行模型，避免后续误判 worker 为死容器。
5. **G6**：trade_cal 一次性 backfill（近1年+明日）能否排进 P0-B（15:00）？观势 18:15 验证引擎与明日 09:26 竞价三时点都可能要它。

## 防doom 自查
本审计全程只读，12 次工具调用 0 错误；未动任何生产容器；未修改 repo 代码（仅新增本审计文件）。

— 督军 2026-10-08 12:15

---
## 终验追加（15:12，cron 71b81282）：P0-A **正式无条件 PASS**
15:10:00 `🔔 CRON FIRED: j_index_daily` 实跑成功（tencent 36行→写6行，success=True，28.5s，dispatch failed=0）；ingest_log 首条业务 scheduled OK 行：run_id=156 rows_written=6 note=date=2026-10-08 codes=6。幂等加分验证：index_daily 当日仍恰 6 行（两次写入 upsert 覆盖无重复）→ R3 对 j_index_daily 解除；j_stock_daily 幂等待 15:30 收盘跑后由 17:50 闸门核（当日总行数应仍=5224）。R2/R4/R5/G6 追问仍开放，铸码 P0-B 间隙答复即可。
