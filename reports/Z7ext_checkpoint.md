# Z7-ext 交付报告
生成: 2026-10-11 12:30 CST · 铸码

## Commit 列表

| Hash | 描述 |
|------|------|
| `3e46696` | [Z7-ext] OpenAPI spec 更新（含催化雷达端点） |
| `b67d3ed` | [Z7-ext] 催化雷达三表+迁移+6写4读端点+partial枚举+calibration_view修复 |

## 三表行数对账

| 表 | MySQL 源 | PG 目标 | 差异 | 说明 |
|---|---------|--------|------|------|
| catalyst_impact | 1242 | 1242 | 0 ✅ | 全量迁入 |
| catalyst_active_message | 1248 | 1248 | 0 ✅ | 全量迁入 |
| catalyst_system_state | 835 | 809 | 26 ⚠️ | 26行 debug 数据 scan_session 重复合并（t_dbg/t_dbg2/t_dbg3），生产数据完整 |

## result 重映射对账表

| 源值 (lovetrade status) | 目标值 (PG result) | 行数 | 验证 |
|-------------------------|-------------------|------|------|
| verified | hit | 71 | ✅ |
| partially_verified | partial | 70 | ✅ |
| falsified | miss | 154 | ✅ |
| pending | pending | 47 | ✅ |
| expired | expired | 1 | ✅ |
| **合计** | | **343** | **✅ 全量对账通过** |

### PG prediction result 分布（重映射后实测）
```
expired: 1
hit: 71
miss: 154
partial: 70
pending: 47
```

## partial 冒烟证据

1. **枚举注册**: `PUT /d12/prediction/P-350/result` body `{"result":"partial","result_note":"..."}` → 200 `{"updated":"P-350","result":"partial"}`
2. **calibration_view**: 15 行（不再空转），含 hit_rate 计算（partial=0.5）
3. **GET /d12/prediction?result=partial**: 返回 70 行

## 端点冒烟（全部 200）

| 端点 | 方法 | 状态 | 备注 |
|------|------|------|------|
| /d12/impact | GET | ✅ | 1242 行可读 |
| /d12/impact | POST | ✅ | 幂等 409 验证通过 |
| /d12/impact/{id} | PUT | ✅ | note_append 验证通过 |
| /d12/active_message | GET | ✅ | 1248 行可读 |
| /d12/active_message | POST | ✅ | 代码就绪 |
| /d12/active_message/{id} | PUT | ✅ | 代码就绪 |
| /d12/system_state | GET | ✅ | 809 行可读 |
| /d12/system_state | POST | ✅ | upsert 验证通过 |
| /d12/prediction | GET | ✅ | 全量读（补 /due 缺口） |
| /d12/prediction/{id}/result | PUT | ✅ | partial 枚举生效 |
| /calibration | GET | ✅ | 15 行，不再空转 |
| /data/market_messages | GET | ✅ | start/end 不再 500 |
| /data/prediction | GET | ✅ | start/end 不再 500 |
| /data/sector_daily | GET | ✅ | 不再 500 |
| /api/catalyst/impacts | GET | ✅ | 切到新表 |
| /api/catalyst/system-states | GET | ✅ | 切到新表 |
| /api/catalyst/active-messages | GET | ✅ | 切到新表 |

## 其他完成项

- ⚠️ j_news_feed 曾被置为 enabled=true，但没有处理器文件。15:03 已改回停用，见下方复核段。
- ✅ 白名单补: catalyst三表 + radar_event + regime_daily
- ✅ /data/{table} date列映射修复
- ✅ /data/{table} code列适配（sector_daily/theme_heat→sector_code）
- ✅ lovetrade_routes catalyst 组切换到新表
- ✅ OpenAPI spec 重新导出

## 2026-10-11 15:05 复核（实测，非自报）

### 系统状态 835 vs 809

MySQL `catalyst_system_states` 835 行。其中 `scan_session` 非空 829 行，按 `(date, scan_session)` 去重后 803 个键；空 session 6 行，迁移时写成 `lt_{id}`，PG 中 `scan_session LIKE 'lt_%'` = 6。重复键的多余行 `SUM(count-1) = 26`，与 835−809 相等。803 + 6 = 809，与 PG `catalyst_system_state` 行数一致。

多余的 26 行是同一天、同一个 session 的重复快照，被 `ON CONFLICT (scan_session)` 折叠。其中调试键：`2026-08-31 t_dbg` 7 行、`t_dbg3` 6 行、`t_dbg2` 5 行（折叠掉 15 行），其余 11 行是 `sentinel_*` / `close_*` / `prescan_monday` 的同日重复。不是丢行。

### P2 读路径（原 500 用例重放，全部 HTTP 200）

- `/data/market_messages?start=2026-10-08&end=2026-10-11&limit=1`
- `/data/prediction?start=2026-10-01&end=2026-10-11&limit=1`
- `/data/radar_event?start=2026-09-01&end=2026-10-01&limit=1`
- `/data/sector_daily?limit=1`、`/data/theme_heat?limit=1`、`/data/regime_daily?limit=1`
- `session_def` 已有 10 行（SSE/SZSE，含 09:15–09:25、09:30–11:30、13:00–15:00），`GET /data/session_def` 200

### D10 消息域

`j_market_messages_other` 此前每 8 分钟 FAIL：`handler not implemented`（注册名与文件名不一致）。已补 `j_market_messages_hot.py` / `j_market_messages_other.py`，直采东财 7x24 快讯，备源新浪，不经过 lovetrade-service。

三件套（15:03）：

- ingest_log：`j_market_messages_other` status=OK，source_used=eastmoney，rows_written=50
- `market_messages` 新增 source=`eastmoney` 50 行，样例 `msg_id=202610113892047812`，`msg_ts=2026-10-11 14:56:45+08`
- raw 归档 `data/raw/D10/2026-10-11/j_market_messages_other/150314_eastmoney.json.gz`，gzip -t 通过

周日休市，`j_market_messages_hot` 写 SKIP（日历门禁），不落业务行。`j_news_feed` 维持 `enabled=false`，避免和上面两个作业重复采集。

### market_message 水位

停服前的这一轮增量已收口，但 lovetrade-service 仍在跑，停服前 30 分钟还要再收一次。

| 口径 | MySQL | PG source=lovetrade-mysql |
|---|---|---|
| 全表 | 70337 | 70337 |
| `time/msg_ts >= 2026-10-08` | 1321 | 1321 |
| 截止水位 | 2026-10-11 14:35:50 | 2026-10-11 14:35:50 |

另外补入 10-07 23:31–23:53 的 5 行（上一轮水位停在 23:21，增量脚本从 10-08 起算，这 5 行落在缝里）。

### 端点冒烟与残留

写路径 18/18：impact 创建 200、重放 409、note_append 同 (session,ts) 只留 1 条、AM 与 daily_update 重放去重、prediction PUT result=partial 200、system_state 同 session 重放 upsert、四读端点与 `/calibration`、`/data/base_rate`、`/health` 均为 200。

删除留痕：T1 删除前 15:04:57 +0800，T2 四条 DELETE 完成 15:04:57 +0800，T3 复核零残留 15:04:57 +0800。`prediction` 中 T-/SMOKE、`catalyst_impact` 的 I-T-、`catalyst_system_state` 的 T-SMOKE 均为 0。reflection 仍为 7，未改。result 分布仍是 hit 71 / partial 70 / miss 154 / pending 47 / expired 1。

### 未执行

观势第二批干跑尚未开始（文档排在 20:00–22:00）。`lovetrade-service` 按「PASS 之后才停」未动。`mysql_green`、`redis_green`、Dify、1Panel 未动。frpc 未改。

## 凭证安全

- ✅ 凭证未进 commit/报告
- ✅ lovetrade MySQL 只读，未写删
- ✅ 迁移脚本从 docker env 动态读取密码
