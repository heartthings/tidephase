# Z7-ext 交接文档 —— lovetrade 退役收尾工程（已做 / 未做 / 方案 / 逻辑）

> 编制：督军 · 2026-10-11 12:3x ｜ 委托方：梁总（拟交其他 agent 完成）
> 所有数字均为督军 2026-10-11 11:54~12:3x 独立实测（非采信任何 agent 自报），文中另注明来源与时点。
> 状态快照会随铸码在飞任务推进而变化——**接手第一步是按 §0.2 重新核对起点**。

---

## 0. 文档目的与接手必读

### 0.1 背景（一段话）

梁总 2026-10-10 裁决：lovetrade-service（Java 遗留行情/催化雷达系统）整体退役，原计划**周日（10-11）夜停服**，周一（10-12）09:00 消费方"观势"（guanshi）运行环全量切换到新数据层 data-api（market-datalayer 仓库，本机 :8787）。观势 10-10 晚做切换盘点+读路径干跑后，开出停服硬门槛清单（Z7-ext）：3 张催化雷达表新建+全量迁移、6 写端点+4 读端点、D12 result 枚举加 partial、legacy prediction 结果重映射等。**本文档 = 这些缺口的完整交接**：哪些已做（含证据）、哪些没做（含精确规格）、每项怎么做（方案与逻辑）、怎么算做完（验收标准）。

### 0.2 ⚠️ 交接协调提示（防冲突，必读）

1. **铸码（zhuma）整改任务仍在运行**：task-998961c12e85，督军 10-11 11:57 派发，死线今日 18:00。截至 12:3x 它已完成相当一部分（见 §3.3"在飞已落项"），工作区有**未提交**产物：`db/migrations/V006__catalyst_three_tables.sql`、`tools/migrate_z7ext.py`、`reports/Z7ext_checkpoint.md`（写作中）、`data_api/main.py`（已改，partial 枚举已加）。
2. 接手 agent 开工前必须：
   - `check_agent_task(task-998961c12e85)` 或问督军，确认铸码任务是否已停/已完成；
   - `cd /home/hello/application/dev/market-datalayer && git log --oneline -8 && git status --short`——若出现 `[Z7-ext]` 前缀 commit 或新增文件，说明铸码又推进了，以**仓库最新实况**为准，在其基础上续做，**严禁推倒重来或重复建表**；
   - 若梁总/督军确认全量移交，应先让铸码任务停下并封存现场，再接手。
3. 规格语义有疑问 → 问观势（guanshi）；协调/验收/停服闸门 → 找督军；范围变更 → 报梁总。

### 0.3 第一手依据文件（本文档的 upstream，冲突时以它们为准）

| 文件 | 路径 | 说明 |
|---|---|---|
| **观势端点规格**（执行首要依据） | `/home/hello/.qwenpaw/workspaces/guanshi/specs/z7ext-endpoint-requirements.md` | 199 行。22 命令替代矩阵、6 写+4 读端点的方法/路径/字段/幂等键全集、迁移范围修正 §三 |
| 观势干跑报告（第一批·读路径） | `/home/hello/.qwenpaw/workspaces/guanshi/reports/dryrun-data-api-read-20261010.md` | 7/10 PASS + 5 项缺陷清单 + 第二批写路径 7 步用例 |
| Z8 迁移 checkpoint | 仓库 `reports/Z8_checkpoint.md` | W0~W2b+LLM 已完成明细、V005 十表对账 |
| Z7 checkpoint | 仓库 `reports/Z7_checkpoint.md` | 数据纠错/D3/D4/D8/Z5 残余明细 |
| 基率校准口径 | 仓库 `docs/base_rate_calibration_spec.md` | partial 计 0.5 = 裁决③；口径 1-5 |
| Z7c 反思层 checkpoint | 仓库 `reports/Z7c_reflection_pack_checkpoint.md` | 已验收关闭，仅需知悉 |

---

## 1. 角色与通信

| 角色 | Agent ID | 职责 | 通信 |
|---|---|---|---|
| 梁总（梁智勇） | —（用户） | 决策人。停服/范围变更/线上操作须其确认或既有裁决授权 | 飞书推送（feishu-push skill） |
| 观势 | `guanshi` | **规格 owner + 唯一消费方**。定义端点语义/迁移口径/验收用例；不直连库，只走 data-api | `chat_with_agent` / `submit_to_agent` |
| 督军 | `dujun` | 协调、派单、独立实测验收、停服闸门核验、飞书通报 | 本文档编制方 |
| 铸码 | `zhuma` | 全栈执行（本波原执行人，任务在飞） | `submit_to_agent` |
| 墨测 | `motest` | 测试（本波暂未派；周一 09:30 竞价复验有其参与） | `submit_to_agent` |

**信息隔离**：财务数据（合同/报价/收支）仅督军掌握，不传给其他 agent；本交接不涉及财务。

---

## 2. 环境与关键路径

### 2.1 新数据层（market-datalayer）

| 项 | 值 |
|---|---|
| 仓库 | `/home/hello/application/dev/market-datalayer`（git，master，**纯本地无远端**——梁总 D4 裁决不备份，风险已留痕） |
| 容器（4 个，docker compose 在 `ops/`） | `market-tsdb`（Postgres+TimescaleDB，宿主 `127.0.0.1:15432`，库 `market_tsdb`，容器内 `docker exec market-tsdb psql -U postgres -d market_tsdb`）/ `market-sched`（APScheduler 调度）/ `market-worker`（采集作业）/ `market-api`（FastAPI，**仅 `127.0.0.1:8787`，永不公网**——梁总 D7 裁决） |
| API 鉴权 | Bearer token 三档（read/write/admin），唯一事实源 `configs/secrets.yaml` → `api.bearer_token_read/write/admin`。历史流传的 `data-api-read-2026-market` 已废弃（401） |
| 凭证文件 | `configs/secrets.yaml`（.gitignore 排除，**绝不进 git/报告/日志**）。段结构：api / database / feishu / longhu / lovetrade / dashscope / web / dify |
| 代码部署方式 | 仓库挂载进容器，**改代码后 `docker restart market-api` 生效**（改迁移/作业则视情况 restart market-sched/market-worker） |
| 作业注册表 | `job_registry`（列名注意：主键列是 `job_name` 不是 job_id/name），种子在 `db/seed_jobs.yaml` |
| 采集验收三件套纪律 | ingest_log 有 OK 行 + 目标表当日 COUNT>0 + raw 归档可解压；跳过必须写 MISS/SKIP 行，禁止静默 |

### 2.2 🔴 大坑一（必看）：lovetrade 源库不在 7511！

- 历史资料（含督军记忆、部分报告）写 lovetrade MySQL = `love_mysql_prod` 容器 `127.0.0.1:7511`（frp 8010）。**实测 2026-10-11 12:0x：7511/7512 端口 CLOSED，`love_mysql_prod`/`love_redis` 容器在 `docker ps -a` 已不存在**（何时消失未查明；redis_green/lovetrade-service 均"Up 15 hours"≈10-10 21:00 重启过，疑同时段整理，不影响本任务）。
- **现状（已实测验证）**：lovetrade 数据库完整居住在 `mysql_green` 容器（Up 6 weeks）：
  - 宿主访问：`127.0.0.1:7507`（root，密码=`docker exec mysql_green sh -c 'echo $MYSQL_ROOT_PASSWORD'`）；
  - docker 网络 `lovetrade` 内：`172.22.0.3:3306`（lovetrade-service 正走此路，12:08 日志仍在正常写入）；redis 同理 = `redis_green`（宿主 7508 / 网内 172.22.0.4）。
- **督军 12:1x 已修** `configs/secrets.yaml` lovetrade 段：`mysql_port: 7507` + 正确密码 + `_note` 说明（改前备份 `configs/secrets.yaml.bak-20261011-z7ext-handover`）。修后已用该段实连成功（impacts=1242 回读 OK）。**迁移脚本一律读 secrets.yaml，不要硬编码，也不要再信 7511。**
- 库内源表实测行数（12:1x，lovetrade 库）：`catalyst_impacts`=1242 ｜ `catalyst_active_messages`=1248（is_active=1 者 37）｜ `catalyst_system_states`=835（max id #922）｜ `catalyst_predictions`=343 ｜ `market_message`=70322（时间列叫 `time`，最新 2026-10-11 11:59:26，**采集仍在跑**）。
- **源库只读铁律**：迁移/核对只准 SELECT，**严禁对 mysql_green.lovetrade 任何写删**——停服前它是唯一事实源；且 mysql_green 容器本体**不在停服范围**（它还承载 datacenter/standard_review_dev 等其他库），今晚只停 `lovetrade-service` 应用容器。

### 2.3 停服对象现状

原口径"周日夜 stop 三容器"已过期：**实际只剩 `lovetrade-service`（7513→8080）一个容器可停**。停法：`docker stop lovetrade-service` 并确认 restart policy 不自动拉起（`docker inspect lovetrade-service --format '{{.HostConfig.RestartPolicy.Name}}'`，若为 always/unless-stopped 需先 `docker update --restart=no lovetrade-service`）。**只 stop 不 rm、不删卷**——图谱资产与库数据留存，随时可起（梁总既有裁决：仅"暂时不用"等级）。frpc 侧 8009 映射成死映射后按惯例只注释不 reload（改 frpc.ini 前先备份）。

---

## 3. 已完成（全部带可复验证据）

### 3.1 昨晚以前（数据层主体，供背景了解）

- **Z1~Z4c**：基建（TimescaleDB 31→57 表、采集框架、dsched 真调度、四角色隔离）、data-api 上线、龙虎端点迁移、10-08 热修（P0-A~D）。门禁①（双跑≥5 交易日）已宣布 **2026-10-08 起算**，最早 10-14 满足。
- **Z8（lovetrade 迁移主体，10-10 20:42~20:46 commit）**：W0 凭证安全化（39ebc7c）；W1 数据补迁 V005 十表全量对账平（topic 253/topic_category 2998/topic_group 180/topic_links 2189/note_category 4/trading_note 84/report 12/dynamic_category_config 12/trading_system_node 25 + catalyst delta 34→25，其中 AM delta 9 行仅 logged）；W2 API 补全 lovetrade_routes 31 端点（catalyst/topic/market/note/report/calendar/home/auth 的**读**+note/trading-system/auth 的写）；W2b 定时任务迁移 6 作业（topic_sync/radar/market_messages×2/plate_intraday/prediction_sync）；LLM DashScope 直连。
- **Z9A/Z9B（10-10 21:21~21:59）**：base_rate 聚合作业实装首跑（16 行）、instrument_master/sentiment_calc/session_def handler 补齐、pct 回填 28 行、global_daily 清理、bidding_list 0→NULL、Emotion 参数固化（只认 ZY 键，Java 源码为据）、reflection_pack 安全+3 口径。
- **Z7c 反思层证据包**：commit 37af45d + 整改 b422c35/9ae81b6；**10-11 10:00 督军复验闸 8/8 项实测 PASS → accepted 关闭**（证据 `reports/Z7c_reflection_pack_checkpoint.md` + 督军 `project_status.json → in_flight.Z7c.reverify_20261011`）。交付：V004 reflection 表、`GET /data/reflection_pack?decision_id=`（四段+gaps 显式缺口）、route_map GET/PATCH（观势自修订权）、j_reflect_daily cron `0f2430a4-b406-4daa-aca1-be5043fbd600`（工作日 18:45，**enabled=false 待观势启用表态**）、周复盘加周度反思节。

### 3.2 今日上午督军实测通过项（11:54~12:0x）

| 项 | 实测证据（12:0x 复测值） |
|---|---|
| Z7-P0-1 数据纠错 | `stock_daily WHERE date='2026-10-10'`=**0**（周六误写 5224 行已删）；10-08/10-09 各 **5224** 完好；`index_daily` 10-10=0；日历门禁 `dworker/core/calendar_gate.py` 上线；trade_cal 10-08 is_open=1 |
| Z7-P1-2 Z5 残余 | OpenAPI **71 路径**；E8 `GET /data/base_rate`→200（16 行起）；E9 `GET /calibration`→200（按月分桶+Brier，当时数据面空转见 §4.④）；D12 四端点在位（POST /d12/cognition、POST /d12/prediction、PUT /d12/prediction/{id}/result、GET /d12/prediction/due→200 返回 200 行 pending） |
| Z7-P0-3 D8 | `dworker/adapters/longhu.py` 无 sleep/RateLimiter/throttle 代码（人为限速已删，docstring 残留"0.5rps"字样=外观问题）；429/403 熔断保留 |
| 竞价整改（task-299af611f075） | commit `6624c7a`；`bidding_list WHERE date='2026-10-09' AND source='tencent'`=**5572 行**；6/9 字段真实数据、3 字段 NULL+note（硬编码 0 已清）。**注意：终判未下**——等周一 10-12 09:30 重验闸（cron `2d7214ad`）看 09:15/09:20/09:25 三时点自然 cron 实盘 |
| 观势侧前置 | 干跑第一批 7/10 PASS；#346~349 终裁已补写回 lovetrade（346/347 verified、348/349 falsified）；close_20261009 快照 #922 已补；测试残留 `P-20261010-001` 库内已不存在（count=0，无需处理） |

### 3.3 铸码在飞任务已落项（12:2x~12:3x 快照，**未提交**，接手前须复核）

| 项 | 实测证据 |
|---|---|
| V006 三表已建 | `catalyst_impact` / `catalyst_active_message` / `catalyst_system_state` 存在于 pg（DDL 见未提交 `db/migrations/V006__catalyst_three_tables.sql`：impact_id PK + lovetrade_id 追溯列 + notes jsonb 追加数组 + detailed_analysis TEXT 不限长；SS scan_session UNIQUE 支持 upsert——均按观势 spec 修 lovetrade 三缺陷） |
| impact 全量迁移 | tsdb `catalyst_impact`=**1242** = 源库 1242 ✅ |
| AM 全量迁移 | tsdb `catalyst_active_message`=**1248** = 源库 1248 ✅（Z8 时"logged only"的 9 行欠账随全量迁移自然覆盖） |
| SS 迁移（部分/待对账） | tsdb `catalyst_system_state`=**809** vs 源库 835 ——差 26 行**未解释**。合理猜测=V006 对 scan_session 建 UNIQUE 后重复轮次被 upsert 去重（源库存在同 scan_session 多行）。**接手必须对账**：`SELECT count(DISTINCT scan_session) FROM catalyst_system_states`（源库）应等于 809；不等则查明 26 行去向并写进 checkpoint |
| result 重映射 | tsdb prediction result 分布=**miss 154 / hit 71 / partial 70 / pending 47 / expired 1**（计 343）——与源库 status 分布（falsified 154/verified 71/partially_verified 70/pending 47/expired 1）**逐项完全吻合** ✅（观势修正三落地；含 #338~352 delta 15 行=verified 7/falsified 5/pending 3 的终裁值） |
| calibration 空转修复 | `calibration_view`=**15 行**（重映射前 0 行）✅ |
| partial 枚举 | `data_api/main.py` L841（未提交改动）：`result not in ("hit","miss","partial","pending","invalid","expired")` ✅（**API 层冒烟未验**，需 restart market-api 后 PUT 实测） |
| market_messages delta | tsdb `market_messages`=**70317 行，max(msg_ts)=2026-10-11 11:59:26**（原止于 10-07 23:21；源库 12:1x 为 70322 且仍在增长——差值为迁移后新增，属正常，停服前跑最后一轮 delta 收口即可） |
| checkpoint 草稿 | `reports/Z7ext_checkpoint.md` 已存在（写作中） |

---

## 4. 未完成（缺口清单 = 交接范围）

> 按优先级排序。①②④是观势明言的停服硬门槛关联项；每项附验收标准。

### ① 6 个写端点 + 4 个读端点（**最大缺口**，实测 grep `/d12/impact|/d12/active_message|/d12/system_state` 命中 0）

规格全部在观势 spec §二（字段/幂等键/语义逐条写死），此处摘要+实现逻辑：

| # | 端点 | 关键语义（照 spec 执行，勿自创） |
|---|---|---|
| 写1 | `POST /d12/impact` | 幂等键=impact_id（客户端生成 `I-YYYYMMDD-NNN`），重复→409 CONFLICT；字段 22 个（spec §二.1 表格：message_type 6 枚举、impact_level 1-5、target_topics jsonb、decay/confidence/global_coupling/lifecycle_stage/remaining_influence 带默认值）；**无副作用**——不得继承 lovetrade"建 impact 自动插 AM"的隐式行为 |
| 写2 | `PUT /d12/impact/{impact_id}` | 部分更新；核心是 `note_append:{ts,session,text}` → append 进 notes jsonb 数组，**追加幂等键=(impact_id,session,ts)，重放去重不重复追加**；可更新 impact_level/lifecycle_stage/remaining_influence/confidence/global_coupling/system_state_after/verified_result(verified/partially_verified/falsified)/verification_note/verified_date；整体 PUT 幂等 |
| 写3 | `POST /d12/active_message` | 幂等键=am_id（=对应 impact_id，1:1），重复→409；daily_updates jsonb 初始 [] |
| 写4 | `PUT /d12/active_message/{am_id}` | `daily_update:{date,stage,remaining_influence,new_developments,ts}` → append 进 daily_updates；**追加幂等键=(am_id,date,ts)**；同日多轮追加是正常语义，同 ts 重放去重；可更新 current_stage/remaining_influence/is_active/expected_decay_date |
| 写5 | `POST /d12/system_state` | **幂等键=scan_session（UNIQUE），重复→upsert 覆盖**（修复 lovetrade"写坏无法修正"缺陷）；overall_note TEXT 不限长、topic_states jsonb 不限键数、sentiment_indicators jsonb 必须可写（三者都是 lovetrade 写 500 的坑） |
| 写6 | `PUT /d12/prediction/{id}/result` 加 `partial` | **代码已改（在飞未提交）**，剩：restart market-api 后实测 PUT result=partial→200 且 calibration 按 **0.5** 计（口径见 docs/base_rate_calibration_spec.md 裁决③；检查 calibration_view/base_rate 聚合 SQL 是否已处理 partial=0.5，**重映射已把 70 行 partial 落库，若聚合 SQL 未认 partial 则 Brier/hit_rate 仍失真——必须核**） |
| 读1 | `GET /d12/impact` | 参数 start/end(date)/stage/min_level/limit(默认200)/impact_id(精确取单卡含 notes 全文)；用途=哨兵拉 note 基线做去重 |
| 读2 | `GET /d12/active_message` | 参数 active=true|false|all(默认active)/stage/limit；返回含 daily_updates 全文 |
| 读3 | `GET /d12/prediction` | 全量读（补 /due 只回 pending 的缺口）：result 多值逗号(hit/miss/partial/pending/invalid/expired)/start/end(按 check_date)/created_start/created_end/limit |
| 读4 | `GET /d12/system_state` | 参数 start/end(date)/scan_session(精确)/limit |

实现约定：命名/返回对齐现有 `/d12/*`（envelope `{data,meta{request_id}}`；错误码 BAD_PARAM/CONFLICT/NOT_FOUND）；写端点 `Depends(require_write)`、读端点 `require_read`；新路由写进 `data_api/main.py`（或独立 router include，注意注册顺序勿被 `/data/{table}` catch-all 遮蔽——现有教训：`/calibration` 曾因督军误测 `/data/calibration` 而虚惊，根级路由要放在 catch-all 之外单独路径）；**改完 `docker restart market-api` + 重导 OpenAPI**（json+yaml，Z7 有现成导出方式，71→约 81 路径）。

**验收**：观势第二批干跑 7 步用例全过（其报告 §四：T- 前缀测试 ID 建 impact→409 幂等→note_append×2 同(session,ts)重放去重→建 AM→daily_update×2 append→建预测→PUT partial→upsert 快照同 session 重放→四读端点回读字段完整性→**测试数据删除留痕三段时间戳**）。

### ② SS 迁移 26 行差异对账（809 vs 835）

逻辑与命令见 §3.3 表内。**验收**：差异原因写进 `reports/Z7ext_checkpoint.md` 对账段（预期=scan_session 去重，需 SQL 证明：源库 `count(DISTINCT scan_session)`=809 且被折叠行内容为同 session 重复快照）；若属真丢行则补齐迁移。**对账不平即停**是全波铁律。

### ③ j_news_feed / D10 消息域停服后不断流（督军已裁决方向：保采集）

- 现状：`j_news_feed enabled=false`；但 job_registry 另有 `j_market_messages_other` / `j_market_messages_hot` **enabled=true**（Z8-W2b 迁入的 lovetrade 作业）。
- **逻辑判断点（接手必做）**：先查这两个作业的 handler 是否实装（`dworker/jobs/` 下有无对应文件、ingest_log 有无其 OK/MISS 行）且**数据源是否独立于 lovetrade**（应为东财/财联社直采；观势哨兵同源已实战验证）。
  - 若已实装且源独立 → D10 消息域已有承接，`j_news_feed` 维持 disabled 并在 checkpoint 注明理由（避免双作业重复采集）；
  - 若未实装/依赖 lovetrade → 启用 j_news_feed 并把 handler 源改为直采（或实装 j_market_messages_* handler），补采 10-08~停服时点缺口。
- **验收**：三件套纪律——ingest_log 出现该作业 OK 行 + `market_messages` 当日新增 COUNT>0 + raw 归档可解压；且用一条含 `source` 字段的样例行证明数据不来自 lovetrade。

### ④ market_message 最后一轮 delta 收口（停服前执行）

源库采集活到停服那一刻（12:1x 已见 11:59 新数据）。**停服前 30 分钟内**跑最后一轮增量（`time > tsdb max(msg_ts)` 的行），对账：源库 count = tsdb count（或差异=停服时点后新增，写明截止水位）。工具基础=`tools/migrate_z7ext.py` 第⑤段（在飞草稿已有）。

### ⑤ P2：读路径小缺陷四项（观势干跑缺陷清单 §三.5，非停服硬阻塞，但顺手全修）

1. `/data/{table}` date 列映射：`market_messages→msg_ts`、`prediction→created_at/check_date`、`radar_event→ts`（带 start/end 查询即 500 "column date does not exist"）；
2. `no_code_tables` 补 `sector_daily`、`theme_heat`（列名 sector_code，ORDER BY code 500）；
3. 白名单补 `radar_event`、`regime_daily`（表在库、白名单缺→TABLE_NOT_ALLOWED）；
4. `session_def` 0 行（10-08 通报项，一直未落；补种子行：09:15-11:30/13:00-15:00 等时段定义，观势现用常量降级，非阻塞）。

**验收**：观势干跑报告中三条 500 的原始 curl 逐一重放→200；`GET /data/radar_event?limit=1`、`GET /data/regime_daily?limit=1`→200。

### ⑥ 工程收尾（缺一不可，"注册≠完成"是本波历史教训）

1. 全部改动 commit（前缀 `[Z7-ext]`，仓库干净，凭证零明文——`tests/` 有现成探针）；
2. `reports/Z7ext_checkpoint.md` 完稿：三表对账（含 SS 26 行解释）、重映射对账表（源值→目标值→行数：verified 71→hit / partially 70→partial / falsified 154→miss / pending 47 / expired 1）、端点清单、j_news_feed 判断结论、P2 修复复测；
3. OpenAPI 重导出（json+yaml）；
4. restart market-api 后全端点冒烟（新 10 端点 + 回归 /calibration /data/base_rate /data/prediction?limit=1 /health）；
5. 回报督军：commit hash 列表 + 对账摘要。督军独立实测后才通知观势跑第二批干跑。

---

## 5. 时间线与协同（今天必须走完）

| 时点（10-11 周日） | 动作 | 责任 |
|---|---|---|
| ~18:00 | Z7-ext 全部交付（§4 ①~⑥），回报督军 | 接手 agent（或铸码在飞任务收尾） |
| 18:00~20:00 | 督军独立实测验收（不看自报，按 §6 清单） | 督军 |
| ≤20:00 | 交付通知观势 → 观势第二批干跑（写路径 7 步用例 + 迁移对账，约 1~2h） | 观势 |
| ~22:00 | 观势终版 PASS/FAIL 报告 | 观势 |
| PASS 后（今晚） | 停服：market_message 最后 delta 收口（§4.④）→ `docker update --restart=no lovetrade-service && docker stop lovetrade-service` → 复核 7513 关闭、mysql_green/redis_green **不动** → frpc 8009 映射注释（先备份 frpc.ini，不 reload） | 接手 agent 执行，督军核验，梁总已裁决授权 |
| FAIL/延迟 | **分支 A**：仅写端点延迟 → 观势 JSONL 降级预案（写落 `data/cache/radar_pending/`，端点上线后补写）带降级过周一，停服可照常；**分支 B**：三表迁移或对账不平 → **停服顺延**，飞书报梁总（feishu-push important），观势判断权已交督军 | 督军裁决 |
| 周一 09:00 | 观势新通道首跑（盘前简报+哨兵首轮全走 data-api；lovetrade skill 标记退役） | 观势 |
| 周一 09:30 | 督军闸门核验（同窗并行：竞价三时点重验闸 cron `2d7214ad` + 龙虎三端点实盘重测——脚本已备 commit `98c9bb8`） | 督军/墨测 |
| 周一 18:45 | j_reflect_daily 首触发前，确认观势启用表态（cron `0f2430a4`，enabled=false） | 督军跟催 |

---

## 6. 督军验收清单（接手 agent 自测用同一套，全部实测命令）

```bash
# 0) token（不回显）
TOKEN=$(grep 'bearer_token_read' configs/secrets.yaml | awk '{print $2}')
WTOKEN=$(grep 'bearer_token_write' configs/secrets.yaml | awk '{print $2}')

# 1) 三表存在+计数（对源库同时点计数，不用本文档旧值）
docker exec market-tsdb psql -U postgres -d market_tsdb -t -c \
 "SELECT 'impact='||count(*) FROM catalyst_impact;
  SELECT 'am='||count(*) FROM catalyst_active_message;
  SELECT 'ss='||count(*) FROM catalyst_system_state;"
docker exec mysql_green sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -D lovetrade -e \
 "SELECT COUNT(*) FROM catalyst_impacts; SELECT COUNT(*) FROM catalyst_active_messages;
  SELECT COUNT(DISTINCT scan_session) FROM catalyst_system_states;"'

# 2) result 分布 = 源库 status 分布（目标 12:2x 值: hit71/partial70/miss154/pending47/expired1）
docker exec market-tsdb psql -U postgres -d market_tsdb -t -c \
 "SELECT result||'='||count(*) FROM prediction GROUP BY result;"

# 3) 新端点冒烟（T-前缀测试数据，用后即删+留痕）
curl -s -X POST -H "Authorization: Bearer $WTOKEN" -H 'Content-Type: application/json' \
  -d '{"impact_id":"I-T-901","date":"2026-10-11","message_summary":"交接冒烟","message_type":"policy","impact_level":3,"target_topics":[],"predicted_effect":"无"}' \
  http://127.0.0.1:8787/d12/impact          # 期望 200/201；重放→409
curl -s -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:8787/d12/impact?impact_id=I-T-901"
# ……其余按观势干跑报告 §四 的 7 步用例逐一执行，最后 DELETE 测试行并记录三段时间戳

# 4) partial 枚举 + calibration 0.5
curl -s -X PUT -H "Authorization: Bearer $WTOKEN" -H 'Content-Type: application/json' \
  -d '{"result":"partial","result_note":"交接冒烟"}' \
  http://127.0.0.1:8787/d12/prediction/P-T-901/result   # 期望 200（先建 P-T-901）
curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8787/calibration | head -c 300  # 非空+含 partial 折半逻辑

# 5) P2 修复复测（观势原 500 用例重放）
curl -s -w '\nHTTP=%{http_code}\n' -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8787/data/market_messages?start=2026-10-08&end=2026-10-11&limit=1"
curl -s -w '\nHTTP=%{http_code}\n' -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:8787/data/sector_daily?limit=1"
curl -s -w '\nHTTP=%{http_code}\n' -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:8787/data/radar_event?limit=1"

# 6) 消息域承接（§4.③ 验收三件套）
docker exec market-tsdb psql -U postgres -d market_tsdb -t -c \
 "SELECT job_name||' '||status||' rows='||rows FROM ingest_log WHERE job_name LIKE '%message%' OR job_name LIKE '%news%' ORDER BY started_at DESC LIMIT 5;"

# 7) 零残留 + 仓库卫生
docker exec market-tsdb psql -U postgres -d market_tsdb -t -c \
 "SELECT count(*) FROM prediction WHERE prediction_id LIKE '%T-9%';"   # =0
cd /home/hello/application/dev/market-datalayer && git status --short && git log --oneline -5  # 干净+[Z7-ext] commits
```

---

## 7. 工程纪律与红线（全波适用，历史教训凝练）

1. **对账不平即停**：任何迁移计数不平 → 停止、写差异报告、报督军；禁止"差不多就行"。
2. **注册≠实装、实装≠完成**：本项目三次踩坑（dsched 空壳心跳、13 handler 未实装、竞价字段硬编码 0 占位）。完成定义=验收三件套（ingest_log OK 行+目标表当日 COUNT>0+raw 归档）或端点实测 200+数据正确。
3. **凭证卫生**：一切凭证只存 `configs/secrets.yaml`；不进 git、不进报告、不进日志、不在命令行回显；改 secrets.yaml 前先带时间戳备份。
4. **MISS 不编数**：源缺数据写 MISS/SKIP 行留痕，禁止硬编码 0/占位值充数（正确姿势=NULL+note）。
5. **禁改冻结面**：观势已实写的 7 条 reflection（id 6-12）不得触碰；prediction 历史行除本波重映射范围外不得改写；lovetrade 源库只读。
6. **API 永不公网**：8787 仅 127.0.0.1（梁总 D7）；不新增任何 frp 映射。
7. **同错 2 次即停**（doom 纪律）：同一错误第二次出现 → 停手换法并报督军。
8. **写操作留痕**：停服类操作（stop 容器、改 frpc、改 restart policy）执行前把命令与输出记入 checkpoint。

---

## 8. 常见坑速查（本项目实测踩过）

| 坑 | 事实 |
|---|---|
| lovetrade DB 端口 | 不是 7511（容器已不存在）→ mysql_green 宿主 7507 / 网内 172.22.0.3:3306；secrets.yaml 已修 |
| API 路由遮蔽 | 根级路由（如 /calibration）别写成 /data/xxx，`/data/{table}` 是 catch-all，表名不在白名单→403 TABLE_NOT_ALLOWED |
| 响应包装 | data-api 返回外层有 `data` 包装（`{"data":...}`），解析别漏 |
| job_registry 列名 | 主键列=`job_name`（不是 job_id/name） |
| trade_cal 列名 | `cal_date`（不是 date） |
| market_message 源表时间列 | 叫 `time`（tsdb 目标表列叫 msg_ts） |
| prediction_id 排序 | 字符串 max 会得 P-99 > P-352（字典序），按数值/created_at 排 |
| market-api 生效方式 | 代码=仓库挂载，改完必须 `docker restart market-api`；核验部署用 `docker inspect market-api --format '{{.State.StartedAt}}'` 对比 commit 时间 |
| 竞价表列名 | bidding_list 用 `date`+`quotations_type`（不是 snapshot_time/trade_date） |
| 冒烟测试数据 | actor='smoke_test' / T-前缀 ID，用后即删，验收查零残留 |

---

## 9. 交付定义（DoD 汇总）

接手 agent 完成的标志 = 以下全部为真且**督军独立实测复核通过**：

- [ ] 三表行数对账平（impact/AM 精确相等；SS 差异有 SQL 证明的去重解释）
- [ ] 6 写+4 读端点上线，观势第二批干跑 7 步用例 PASS，测试数据零残留
- [ ] partial 枚举实测 200 且 calibration/base_rate 按 0.5 计（calibration_view 非空、含 partial 贡献）
- [ ] result 分布与源库 status 分布逐项吻合（12:2x 基准：hit 71/partial 70/miss 154/pending 47/expired 1）
- [ ] D10 消息域承接结论落地（j_market_messages_* 实装核验 或 j_news_feed 启用改源），三件套证据齐
- [ ] 停服前 market_message 最后 delta 收口对账（写明截止水位）
- [ ] P2 四项修复且原 500 用例重放 200
- [ ] OpenAPI 重导出、[Z7-ext] commits、仓库干净、Z7ext_checkpoint.md 完稿
- [ ] 观势终版 PASS → 停服执行（只 stop lovetrade-service，restart=no，卷/库保留）→ 周一 09:00 新通道首跑 → 09:30 督军闸门核验

---

*编制依据：督军 2026-10-11 11:54~12:3x 全程实测（git log/仓库文件/pg 计数与分布/mysql_green 源库计数/端口探测/docker 网络与容器状态/API curl 冒烟/观势两份文件全文/铸码在飞任务工作区快照）。本文档不含任何明文凭证。*
