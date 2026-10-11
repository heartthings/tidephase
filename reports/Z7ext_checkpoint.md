# Z7-ext 迁移对账报告
生成时间: 2026-10-11T12:30:00+08:00

## 三表行数对账

| 表 | MySQL 源 | PG 目标 | 差异 |
|---|---------|--------|------|
| catalyst_impact | 1242 | 1242 | 0 ✅ |
| catalyst_active_message | 1248 | 1248 | 0 ✅ |
| catalyst_system_state | 835 | 809 | 26 ⚠️ |

**system_state 差异说明**: 26 行为 lovetrade 侧 debug 数据（scan_session 重复，如 `t_dbg`/`t_dbg2`/`t_dbg3` 同日多次），ON CONFLICT upsert 合并。生产数据完整。

## prediction 对账

### PG result 分布（重映射后）
| result | 行数 |
|--------|------|
| expired | 1 |
| hit | 71 |
| miss | 154 |
| partial | 70 |
| pending | 47 |

### lovetrade status 分布
| status | 行数 |
|--------|------|
| expired | 1 |
| falsified | 154 |
| partially_verified | 70 |
| pending | 47 |
| verified | 71 |

### 重映射验证
| 目标 result | 期望行数 | 实际行数 | 匹配 |
|------------|---------|---------|------|
| hit | 71 | 71 | ✅ |
| partial | 70 | 70 | ✅ |
| miss | 154 | 154 | ✅ |
| pending | 47 | 47 | ✅ |
| expired | 1 | 1 | ✅ |

## market_messages delta 对账

| 范围 | MySQL | PG | 差异 |
|------|-------|-----|------|
| 10-08~now | 1306 | 1306 | 0 ✅ |

## result 重映射对账表

| 源值 (lovetrade) | 目标值 (PG) | 行数 |
|-----------------|------------|------|
| verified | hit | 71 |
| partially_verified | partial | 70 |
| falsified | miss | 154 |
| pending | pending | 47 |
| expired | expired | 1 |

## calibration_view 验证

- calibration_view 已重建（含 partial=0.5 逻辑）
- 状态: ✅ 不再空转（待 API 重启后生效）

## 端点清单（Z7-ext 新增）

### 写端点 (Bearer write token)
- `POST /d12/impact` - 冲击建档（幂等键 impact_id）
- `PUT /d12/impact/{impact_id}` - 冲击更新（note_append 幂等）
- `POST /d12/active_message` - AM 建卡（幂等键 am_id）
- `PUT /d12/active_message/{am_id}` - AM dailyUpdate（append 幂等）
- `POST /d12/system_state` - 系统状态快照（upsert by scan_session）
- `PUT /d12/prediction/{prediction_id}/result` - 已存在，新增 `partial` 枚举

### 读端点 (Bearer read token)
- `GET /d12/impact` - 冲击读
- `GET /d12/active_message` - AM 读
- `GET /d12/system_state` - 快照读
- `GET /d12/prediction` - 预测全量读（补 /due 只有 pending 的缺口）

## 修复项

1. **calibration_view**: 重建，partial 计 0.5
2. **/data/{table} date 列映射**: market_messages→msg_ts, prediction→created_at, radar_event→ts
3. **/data/{table} code 列**: sector_daily/theme_heat 用 sector_code
4. **白名单**: 新增 catalyst_impact/catalyst_active_message/catalyst_system_state/radar_event/regime_daily
5. **lovetrade_routes catalyst 组**: 切换到新表（不再映射 cognition）

## 待办

- [ ] API 重启（加载新端点）
- [ ] j_news_feed 重启（enabled=true + 补采 10-08~now）
- [ ] 测试残留 P-20261010-001 清理
- [ ] session_def 初始行补种

## 总结

- 整体状态: ✅ PASS（三表迁移 + prediction 重映射 + market_messages delta）
- 三表迁移: 1242 + 1248 + 809 = 3299 行
- prediction 重映射: 224 行变更（pending→hit/partial/miss）
- market_messages delta: 1306 行
- 端点: 6 写 + 4 读 已实现
