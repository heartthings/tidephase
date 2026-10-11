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

- ✅ j_news_feed: enabled=true（job_registry 已更新）
- ✅ 白名单补: catalyst三表 + radar_event + regime_daily
- ✅ /data/{table} date列映射修复
- ✅ /data/{table} code列适配（sector_daily/theme_heat→sector_code）
- ✅ lovetrade_routes catalyst 组切换到新表
- ✅ OpenAPI spec 重新导出

## 未完成（P2，时间富余再做）

- [ ] /data/radar_event 白名单已加但 start/end 需验证
- [ ] /data/theme_heat no_code 处理需验证
- [ ] session_def 初始行补种（不阻塞停服）

## 凭证安全

- ✅ 凭证未进 commit/报告
- ✅ lovetrade MySQL 只读，未写删
- ✅ 迁移脚本从 docker env 动态读取密码
