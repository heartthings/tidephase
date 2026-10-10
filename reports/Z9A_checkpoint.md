# Z9-A 今夜清板 Checkpoint

> 开始时间：2026-10-10 21:30
> 指令：梁总直接指令，不规划不配速，干完为止

---

## P0-1 T3.1 base_rate 聚合作业实装

### 状态：🔄 进行中

### 地面真相（督军 21:05-21:25 实测 + 铸码确认）
- prediction: 344 行（72 hit / 0 miss / 271 pending / 1 expired）
- regime_at_create: 全为空字符串（lovetrade 迁移数据未设 regime）
- horizon: NULL 或 T1（大部分 NULL）
- category: continuation(223) / phase_change(43) / reversal(37) / spillover(37) / 产业(3) / 情绪(1)
- trade_cal: 0 行（无交易日历，用日历日近似 90 交易日≈130 日历日）
- base_rate 表已存在（V003 已应用），PK=(regime,category,horizon,window_end)，0 行
- V003 未登记 schema_migrations

### 子步骤
- [x] 读取 spec（docs/base_rate_calibration_spec.md v1.0 冻结版）
- [x] 确认 DB 现状（prediction/base_rate/trade_cal/schema_migrations）
- [ ] 写 j_base_rate.py handler
- [ ] seed_jobs.yaml 注册 j_base_rate
- [ ] V003 补登记 schema_migrations
- [ ] 本地 import 校验
- [ ] 手动实跑一次
- [ ] 验证 SELECT count(*) FROM base_rate > 0
- [ ] 验证 GET /data/base_rate 返回非空
- [ ] 验证 GET /calibration 返回非空
- [ ] commit + 回报

### 口径决策（严格遵循 spec v1.0）
- regime 空字符串 → 存为 'unclassified'（base_rate.regime NOT NULL）
- horizon NULL → 存为 '_unknown'
- 窗口：rolling_90 用 130 日历日近似（trade_cal 空）
- expired 不计入 n 分母（口径2）
- Wilson 95% CI 计算
- reliability: <5=low, <20=medium, >=20=high

---

## P0-2 Z9 lovetrade-web 接口改指 data-api
### 状态：⏳ 待开始

## P0-3 handler 补齐
### 状态：⏳ 待开始

## P0-4 竞价九字段确认
### 状态：⏳ 待开始
