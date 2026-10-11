# Z10 开市前交接点 · 2026-10-11 20:40

给观势干跑。数字都是本机实测，不是计划。

## 明天会不会响

修了一个调度错位：APScheduler 的周几是周一=0，种子里的 cron `1-5` 被当成周二到周六。周六 10-10 的采集就是这么误触发的，周一 10-12 原本不会触发。

`dsched/main.py` 已把标准 cron 周几转成 `mon-fri`。调度进程 20:30 重启后，下一跳是：

- `j_global_overnight` 2026-10-12 07:30
- 竞价三快照 09:15 / 09:20 / 09:25
- `j_prediction_sync` 不在调度列表里（已停用）

## P0

| 项 | 结果 |
|----|------|
| P0-1 lovetrade | 容器、镜像、库 `lovetrade` 在今晚更早已经删除，不是停着等。mysql_green / redis_green 没动。外网 8009 不再是 lovetrade |
| P0-2 `j_prediction_sync` | `enabled=false`。种子文件同样是 false，重启不会被种回去。预测只走 `POST /d12/prediction` |
| P0-3 P-350/351/352 | `check_date=2026-10-16`，`horizon=W1`，`conditions.wp_code` 分别为 `WP-2026W42-001/002/003`。原 `lovetrade_id` 保留 |
| P0-4 干跑行 | `I-T-001`、`AM-T-001`、`P-T-001`、`T_dryrun*` 7 行已删。prediction 的 hit 回到 71，`calibration_view` 回到 15。删除留痕在 `ingest_log.job=ops_p0_20261011` |
| P0-5 `POST /d12/regime_daily` | 已上线，write token，按 `date` upsert。regime 枚举：stable / oscillation / critical / transition / trending_up / trending_down / news_shock。非法值 400。表增加 `note`、`indicators`（V008）。探针行 `2099-01-01` 已删，表仍是 0 行，等观势 17:30 写 |

`POST /d12/system_state` 的 `scan_time` 不是 `HH:MM` 或 `HH:MM:SS` 时返回 400 `BAD_PARAM`，不再把数据库报错原样抛出。

OpenAPI 已重导：`docs/openapi_z7ext.json`，87 条路径，含 `/d12/regime_daily`。

## 补上的数据（验收三件套）

| 作业 | ingest | 表 | raw |
|------|--------|----|-----|
| `j_zt_pools` | OK 87 / 90 | zt 42+69，炸板 32+13，跌停 13+8（10-08 与 10-09） | `data/raw/D3/2026-10-11/j_zt_pools/` |
| `j_sector_daily` | OK 518 / 518 | sector_daily 与 theme_heat 各 259 行 × 两天。锂电池 801004：10-08 涨幅 0.662、主力 35.39 亿；10-09 涨幅 0.674、主力 29.22 亿 | `data/raw/D6/2026-10-11/j_sector_daily/` |
| `j_fund_flow` | OK 5727 | 个股 5498、板块 229，日期 2026-10-09。和 `stock_daily` 抽样 8/8 对上 | `data/raw/D4/2026-10-11/j_fund_flow/` |

源和缺口（不编数）：

- 涨停池主源是同花顺。东财 push2ex 本机返回 `rc=205`。**昨涨今现 `yzt_pool` 仍是 0 行**：同花顺没有带日期的昨涨今现接口。
- 板块主源是龙虎 `RealRankingInfo` `ZSType=7`，代码继续用 `801xxx`。腾讯 `pt01` 只能报出其中 49 个，已不用它做主源。
- 个股资金流主源是新浪。只有超大单 `r0_net`、小单 `r3_net`。**主力 / 大单 / 中单是 NULL**。板块资金流的代码是新浪分类（`gn_*` / `new_*`），和 `sector_daily` 的 `801xxx` 不是同一套，按名称对照，不要按代码 join。新浪没有历史页，**10-08 的资金流没有补**。
- 竞价三快照的源从只剩东财改成腾讯优先。`j_bidding_list`（09:26 终版）维持停用：三个快照才是盘中触发点，09:26 那次是整改后故意关掉的。代码改为按证券主档拉真实代码，不再扫空号段。非交易日写 SKIP。

## 观势明天可以怎么验

1. `GET /d12/prediction/due?date=2026-10-12` 不应再把 P-350/351/352 当到期。这三条的 `check_date` 是 2026-10-16。
2. `GET /data/job_registry` 里 `j_prediction_sync.enabled` 为 false。
3. `POST /d12/regime_daily` 用 write token 写 2026-10-12，再 `GET /data/regime_daily` 读回。幂等再写一次应覆盖同一天。
4. `GET /data/zt_pool?start=2026-10-09&end=2026-10-09`、`/data/sector_daily`、`/data/fund_flow_stock` 行数与上表一致。
5. 07:30 之后看 `j_global_overnight` 有没有新的 OK。09:15 之后看三份竞价快照。那是开市后的第一段实盘，今晚无法预演。

## 今晚没做、不要当成已经好了

这些作业仍然 enabled，但没有 handler，到点会记 FAIL「handler not implemented」：`j_etf_daily`、`j_margin_daily`、`j_block_trade`、`j_holder_num`、`j_valuation`、`j_index_minute`、`j_announcements`、`j_corporate_actions`、`j_macro_indicators`、`j_backfill_daily`、`j_coverage_check`、`j_daily_report`、`j_verify_daily`。收盘分析如果吃 ETF、两融、大宗、分钟线，明天还是空的。

`news_telegraph` 停在 09-30。弃用还是另开采集，仍是梁总的决定，没有擅自接。

观势台（原 lovetrade 前端）已经是容器 `market-console`，本机 `127.0.0.1:7511`，FRP 远端 `8005`。部署方式那一项不再悬着。
