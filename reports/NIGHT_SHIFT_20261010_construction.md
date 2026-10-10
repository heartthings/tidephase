# 夜间施工报告 · 2026-10-10（周六）21:04 → 收工

> 督军 ｜ 触发：梁总直接指令（观势 21:04 转达）「把表中的所有任务今晚都干完。这么久没干完是不是按预计完成时间规划的？不要规划，直接开干，直到全部完成。」
> 纪律执行：不规划不配速 ／ 完成一项推一项 ／ 阻塞立即飞书不隔夜 ／ 同错 2 次即停换法 ／ 值级核实（不轻信 Agent 自报）

---

## 一、时间线（实测时刻，非计划时刻）

| 时刻 | 动作 | 结果/证据 |
|---|---|---|
| 21:04 | 收到指令，先做地面真相扫描（不信任何既有报告） | DB 60 表逐表 COUNT、活体 openapi、job_registry、cron、marker、specs 产物 |
| 21:05 | 核出 6 处"报告与实况不符" | 见第二节 |
| 21:16 | 并行派工：铸码 Z9-A（background）+ 墨测 M3（background） | task-10cc0ab3331a / task-93a2b7e79dfd |
| 21:20 | 重启 market-api（先容器内 import 干跑校验）→ 活体 openapi **20 → 50 paths** | Z8-W2 的 31 端点此前"已提交未生效" |
| 21:20 | 补 `ops/requirements-api.txt` 缺 `requests`（否则重建镜像即崩）+ 容器内 pip 安装 | 拆掉一颗雷 |
| 21:20 | 重启 market-sched → seed 生效，job_registry **33 → 38** | 6 个 lovetrade 作业 enabled=true |
| 21:22 | 启用 j_reflect_daily cron（`0f2430a4`，18:45 mon-fri）| 此前 enabled=false → **今日 18:45 未跑**，如实上报 |
| 21:23 | D12 写端点 live 全链路验证（403/401/400/409/200 + 落库 + 当场删净） | `reports/D12_write_endpoint_live_verification.md` |
| 21:23 | Z5/T3.5 交付面落 `guanshi/specs/`：openapi.json(50) + data_api_client_example.py + D12 验证报告 | 三件已核 |
| 21:25 | 清理 D12 测试残留：`F-001`(测试认知/src=test) + `P-20261010-001`(测试预测) | 否则观势 seeding 撞 409；删前逐行 JSON 快照留档 `reports/TEST_RESIDUE_CLEANUP_20261010.md` |
| 21:30 | sentiment 回填第一次尝试 → **0 条**（工具与适配器同病） | 不猜、不重试同法：转去读 Java 源码 |
| 21:33 | 按 `SpeculativePerformanceDataParamBuilder.java:71-96` 逐参复刻请求 → 源端返回 **ZY 30 条** | 根因=我方参数不全（缺 st/apiv/VerSion/PhoneOSNew/index + DeviceID 大小写 + Dalvik UA） |
| 21:35 | 探测源端上限：st=60/90/120/250 → **125 交易日**（2026-04-03~10-09） | 1 次请求即可，无需分页 |
| 21:38 | sentiment_daily **0 → 125 行**，源库逐条交叉 **0 不一致**，raw 归档 + ingest_log 留痕 | `reports/sentiment_backfill_20261010.md` |
| 21:40 | 复测反思证据包：`SENTIMENT_DAILY_EMPTY` gap **已消除**（P-200/P-261/P-346 三条 S1.sentiment 均返回真实行） | 顺带核出 4 个反思包缺陷（含 1 个 SQL 注入面） |
| 21:45 | 追加 `URGENT_FROM_DUJUN.md` 第 6 节（4 缺陷 + curl 原文） | 与在途 Agent 用文件通道通信，避免抢改同一文件 |
| 21:47 | 提前给观势发解锁信号（不等收工报告）：seeding 可开始 + 三项数据义务 + 历史闭环反思批次建议 | task-bb912137aa06 |
| 21:50 | 铸码 Z9-A 回报 → **逐项值级核实**：base_rate=16 行✅、V003 已补登✅、instrument_master=5574✅、session_def=10✅ | 同时核出 **1 处结论不实 + 3 个数据缺陷** |
| 21:52 | 核出铸码"三字段有值 100 行"不实：那 100 行是 10-09 eastmoney 批的**硬编码 0 残留**（qtype=2） | 记名（G7 同类第 4 次变形），要求今后报"值分布"而非 NOT NULL 行数 |
| 21:55 | 派铸码 Z9-B 修复波（B1~B6） | task-59c96888eefa |
| 21:50 | 墨测 M3 回报 → 独立抽检复核其结论 | 见第三节 |
| 22:08 | **督军独立复核 T3.8**：10-09 六指数 close/open/high/low 与腾讯官方逐值一致 | 3813.79 / 2807.46 / 4317.25 / 1457.27 / 12641.86 / 3043.33 |
| 22:10 | 飞书推送第 2 批（含 2 项需梁总裁决） | important |
| 22:15 | 飞书任务表 **27 条**逐条更新（状态+证据化备注），回读校验 27/27 写入成功 | 观势Agent 项目：已完成 20 / 进行中 16 / 未开始 11 = 47 |
| 22:20 | 核 Z9 web 构建产物：baseURL 已烧入、旧 Java 地址 8009/8080 **零残留**、dist 18M/60 assets | 部署访问方式需梁总裁决（本机无该 web 的容器/nginx/frp） |

---

## 二、开工 15 分钟内核出的"报告与实况不符"（这是拖慢的真凶，不是排期）

| # | 既有口径 | 实测真相 | 处置 |
|---|---|---|---|
| 1 | Z8-W2「OpenAPI 总路径 50」已完成 | 活体只有 **20 paths**，31 端点未加载（容器 20:05 起、代码 20:42 提交） | 21:20 重启 → 50 paths 实证 |
| 2 | 同上，且 `requirements-api.txt` 缺 `requests` | 容器内 `import data_api.main` **ModuleNotFoundError** → 一旦重建/重启即崩 | 补依赖 + 容器内安装，雷已拆 |
| 3 | Z8-W2b「6 作业注册」已完成 | `job_registry` 仍 **33 行**，5 个新作业未入库（seed 只在 sched 启动跑） | 21:20 重启 → 38 行实证 |
| 4 | j_reflect_daily「已注册，18:45 我要用」 | **enabled=false** → 今日 18:45 从未触发；观势侧 8 个 cron 全 disabled | 21:22 启用 + 如实上报；其余 cron 不代观势决定 |
| 5 | 「backfill.py 3 年回填」待跑 | 梁总 10-10 **D3 裁决已终止 3 年回填**，改近一周（库内 10-08/10-09 已满足） | 不执行（执行即违裁决），改为量化六案例回填代价上报 |
| 6 | 「现在就是交易时段，立即做盘中 smoke」 | 今天**周六休市**（trade_cal: 10-10/10-11 is_open=0） | 物理挂起到周一 09:15/20/25，不伪造盘中数据 |
| 7 | Z7「Emotion 实测响应顶层为 list（空），兼容双键」 | **误判**：源端正常，是我方请求参数不全；补齐后返回 ZY 125 条 | 21:38 回填 sentiment 125 行；参数集交铸码固化；撤回原结论 |

---

## 三、今夜完成项（全部带证据路径，督军已亲自复核）

### 数据层
1. **sentiment_daily 0 → 125 行**（2026-04-03~2026-10-09，龙虎 Emotion st=250 源端上限）
   - 源库逐条交叉 **0 不一致**；raw 归档 `data/raw/D3/2026-10-10/j_sentiment_calc/`；`ingest_log` trigger=backfill 留痕
   - 证据：`reports/sentiment_backfill_20261010.md`
   - 连带效果：反思证据包 `SENTIMENT_DAILY_EMPTY` gap 消除
2. **base_rate 0 → 16 行**（T3.1，按冻结 spec v1.0，含 wilson_ci_95 / reliability / window_type）+ V003 补登 `schema_migrations`
   - `GET /data/base_rate`、`GET /calibration` 实测返回真实数据
   - ⚠️ 诚实警告：**hit_rate 全 1.0**（prediction 343 条=hit72/expired1/**miss0**）→ 校准当前**无判别力**，需观势侧如实写 miss 样本，数据层无法代补
3. **instrument_master 1 → 5,574 行**（全市场 A 股）；**session_def 0 → 10 行**（SSE/SZSE 时段静态配置）→ G6 前置缺口第 3 天终于闭环
4. **D12 写端点 live = PASS**：鉴权/校验/写入/幂等四链全测，smoke 记录当场删净（cognition 2,077 / prediction 343 未污染）
   - 证据：`reports/D12_write_endpoint_live_verification.md`
5. **测试残留清理**：F-001 + P-20261010-001（删前 JSON 快照留档）→ 观势 F-001~F-010 命名空间释放
6. **job_registry 33 → 38**；**活体 openapi 20 → 50 paths**

### 验收面
7. **T3.8《对比基线报告》**（梁总亲自比对用）：抽样 89 项，**A股 82/82 精确匹配**（六指数 OHLC vs 腾讯 + 新浪双源交叉、10 只个股 vs 腾讯，浮点差 <0.01）；全球品种 7 项源不可达如实标注
   - 督军 22:08 独立复核六指数 10-09 逐值一致 → **可作切源依据**
   - 证据：`reports/T38_baseline_comparison.md` + `guanshi/specs/`
8. **M2 Phase2 独立抽检 v2 = PASS**：源端 26 表 467,639 行（独立解析今晚 20:43 的 114M dump）vs 新库；四项历史差异全部归因
   - index_trend 52,196 = index_minute 39,182 + quarantine 13,014（隔离 100% = STAR50 指数类型未映射，**无数据丢失**）
   - market_message 70,263 → 69,011（差 1,252=1.8% 迁移过滤）；market_radar 298,495 → 296,749（差 1,746=0.6%）；trading_calendar 367 → 396（PG 主动扩一个月日历）
   - 证据：`reports/M2_phase2_lovetrade_audit_v2.md`
9. **六案例核对单 v2**：六案例仍全 FAIL；较 v1 改善 D6 全缺→✅、D10 C3-C6→✅；D2/D3 缺失根因=**梁总 D3 裁决**（非施工遗漏）；回填清单量化 ≈234,224 行
   - 证据：`reports/phase3_six_case_witness_v2.md` + `guanshi/specs/replay_witness_filled.md`
10. **Z9 lovetrade-web**（源码 21:09 到手当夜开工）：接口调用改指 data-api（`/api/` 前缀 + `code:0` 兼容，lovetrade_routes 扩至 **55 路由**）；dist 构建完成（buildTime 21:27:56，18M/60 assets）；产物内 baseURL=`http://127.0.0.1:8787`，旧 Java 地址 **零残留**

### 管理面
11. **飞书任务表 27 条更新**（状态 + 证据化备注），回读校验 27/27；观势Agent 项目分布=已完成 20 / 进行中 16 / 未开始 11（共 47）
12. **飞书推送 2 批**（21:36 important 6 项 / 22:10 important 含 2 项裁决请求）
13. **提前解锁观势**（21:47）：不等收工报告，先把 seeding 阻塞排除并告知三项数据义务

---

## 四、今夜核出的缺陷（已派 Z9-B，证据=SQL/curl 原文）

| # | 级别 | 缺陷 | 实测证据 |
|---|---|---|---|
| B1 | P0 | `index_daily.pct` **28 行 NULL**（09-16/09-30/10-08/10-09）：历史迁移行有值，**我们自己的 j_index_daily(tencent) 不写 pct** | `count(pct)=1585/1613`；腾讯接口本就返回昨收（我已实测可算） |
| B2 | P0 | `global_daily` eastmoney 分支**字段错位**：4 行 pct 里塞的是价格；N225 close=69544 明显错（同日 NK225=44946.64）；**品种 code 分裂** N225/NK225 并存 → 序列断裂 | DJI/SPX/IXIC@10-07、N225@10-08 全部 src=eastmoney |
| B3 | P1 | `bidding_list` 100 行（10-09 eastmoney, qtype=2）三字段 **硬编码 0 残留**，被报成"有值" | `notnull=100 / 零值=100 / tencent 批 5572 行全 NULL` |
| B4 | P0 | Emotion 参数集需固化进 adapter/handler；**删除基于误判的"顶层 list 兜底"**，改为空载荷→MISS 行+告警 | 见 `URGENT_FROM_DUJUN.md` §1（含 Java 源码行号） |
| B5 | **P0 安全** | 反思包 S2 把 `falsify.metric` **原样拼进 SQL**（注入面）：P-346 的 metric 是 JSON 串 → SQL 语法错误 | `S2_QUERY_ERROR: syntax error at or near ":"`；routed_table 被切成 `{"rangeLow": -1` 碎片 |
| B5② | P1 | S3 regime 窗口**起止倒挂** → 即使观势开始写 regime_daily，S3 也永远空 | `No regime_daily for 2026-09-01~2026-08-31`（P-261）、`2026-10-10~2026-10-09`（P-346） |
| B5③ | P1 | `GLOBAL_OVERNIGHT_EMPTY` 用**自然日**查隔夜数据（周日误报） | P-261 查 2026-08-30=周日；global_daily 实有 674 行/324 交易日 |
| B5④ | P1 | `VOLUME_ERROR` 的 reason 是字符串 `"0"`（错误信息丢失） | 应拆 VOLUME_EMPTY / VOLUME_QUERY_ERROR 并附窗口与异常原文 |
| B6 | P1 | `sector_daily` 只有 kind='concept'、止于 09-30 → 所有决策 S1.sector 常亮 gap；`theme_heat=0` | 11,318 行全部来自 lovetrade plate_movement 迁移；j_sector_daily handler 未实装 |
| — | 记名 | 铸码"字段有值"结论不实（G7 同类**第 4 次变形**）；Z7"源端空"误判（第 3 次变形） | 已要求：字段完成度必须报"值分布"（notnull/零值/NULL 三个数）；**同错第 5 次停线** |

---

## 五、在途（收工时状态）

- **铸码 Z9-B**（task-59c96888eefa，21:55 派）：B1 pct / B2 global 错位 / B3 清理 / B4 Emotion 固化 / B5 反思包 4 缺陷 / B6 sector_daily + web 部署
- **待我做**：Z9-B 落地后重启 market-api（加载 55 路由）与 market-sched（注册 j_base_rate/j_instrument_master）→ 复验 openapi paths、reflection_pack 四缺陷是否消除、pct NULL 是否归零
- **观势侧**（已 21:47 通知）：F-001~F-010 seeding + 历史闭环反思批次（73 条已关闭决策，建议先跑最近 5~10 条）+ 三项数据义务（regime_at_create / reasoning_trace+alternatives / falsify 标准 schema）
