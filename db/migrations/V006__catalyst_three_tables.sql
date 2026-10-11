-- V006: 催化雷达三表（impact / active_message / system_state）
-- Z7-ext · 2026-10-11 · 铸码实装
-- 依据: 观势 specs/z7ext-endpoint-requirements.md §二
-- 修复 lovetrade 三大缺陷: overall_note 500截断→TEXT不限长; topic_states 7键限→JSONB不限; sentiment_indicators 写入500→JSONB不限

-- ─── catalyst_impact ─────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS catalyst_impact (
    impact_id           VARCHAR(32) NOT NULL PRIMARY KEY,  -- 客户端生成 I-YYYYMMDD-NNN 或迁移保留 lovetrade_id
    lovetrade_id        BIGINT,                             -- 迁移来源 ID（可追溯）
    date                DATE NOT NULL,
    scan_session        VARCHAR(64),
    message_summary     TEXT NOT NULL,
    message_source      VARCHAR(200),
    message_url         TEXT,
    message_time        TIMESTAMPTZ,
    message_type        VARCHAR(30) NOT NULL,               -- global_market/policy/earnings/industry/geopolitical/breaking_event
    impact_level        SMALLINT NOT NULL CHECK (impact_level BETWEEN 1 AND 5),
    target_topics       JSONB NOT NULL DEFAULT '[]',        -- [{topicName, group}]
    system_state_before JSONB,
    system_state_after  JSONB,
    predicted_effect    TEXT NOT NULL,
    detailed_analysis   TEXT,                                -- 不限长（修复 lovetrade 截断）
    decay_days          INT DEFAULT 3,
    decay_type          VARCHAR(20) DEFAULT 'normal',       -- fast/normal/slow/pulse
    confidence          NUMERIC(3,2) DEFAULT 0.50,
    global_coupling     VARCHAR(10) DEFAULT 'medium',       -- strong/medium/weak/decoupled
    lifecycle_stage     VARCHAR(20) DEFAULT 'shock',        -- shock/fermentation/spread/decay/closed
    remaining_influence NUMERIC(3,2) DEFAULT 1.00,
    verified_result     VARCHAR(30),                        -- verified/partially_verified/falsified
    verification_note   TEXT,
    verified_date       DATE,
    notes               JSONB NOT NULL DEFAULT '[]',        -- note_append 追加数组 [{ts, session, text}]
    actor               VARCHAR(64) DEFAULT 'guanshi',
    source              VARCHAR(64) NOT NULL DEFAULT 'lovetrade-mysql',
    ingest_ts           TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_time        TIMESTAMPTZ,
    updated_time        TIMESTAMPTZ
);
COMMENT ON TABLE catalyst_impact IS 'D12 催化冲击卡（Z7-ext 新建）';

CREATE INDEX IF NOT EXISTS idx_impact_date ON catalyst_impact(date);
CREATE INDEX IF NOT EXISTS idx_impact_stage ON catalyst_impact(lifecycle_stage);
CREATE INDEX IF NOT EXISTS idx_impact_level ON catalyst_impact(impact_level);
CREATE INDEX IF NOT EXISTS idx_impact_session ON catalyst_impact(scan_session);
CREATE INDEX IF NOT EXISTS idx_impact_lovetrade ON catalyst_impact(lovetrade_id);

-- ─── catalyst_active_message ─────────────────────────────────────────

CREATE TABLE IF NOT EXISTS catalyst_active_message (
    am_id               VARCHAR(32) NOT NULL PRIMARY KEY,   -- = 对应 impact_id（1:1）
    lovetrade_id        BIGINT,
    impact_id           VARCHAR(32) NOT NULL,                -- FK → catalyst_impact.impact_id
    message_title       TEXT NOT NULL,
    current_stage       VARCHAR(20) NOT NULL DEFAULT 'shock',
    remaining_influence NUMERIC(3,2) NOT NULL DEFAULT 1.00,
    is_active           BOOLEAN NOT NULL DEFAULT true,
    expected_decay_date DATE,
    daily_updates       JSONB NOT NULL DEFAULT '[]',        -- [{date, stage, remaining_influence, new_developments, ts}]
    source              VARCHAR(64) NOT NULL DEFAULT 'lovetrade-mysql',
    ingest_ts           TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_time        TIMESTAMPTZ,
    updated_time        TIMESTAMPTZ
);
COMMENT ON TABLE catalyst_active_message IS 'D12 活跃消息卡（与 impact 1:1，Z7-ext 新建）';

CREATE INDEX IF NOT EXISTS idx_am_active ON catalyst_active_message(is_active);
CREATE INDEX IF NOT EXISTS idx_am_stage ON catalyst_active_message(current_stage);
CREATE INDEX IF NOT EXISTS idx_am_impact ON catalyst_active_message(impact_id);
CREATE INDEX IF NOT EXISTS idx_am_lovetrade ON catalyst_active_message(lovetrade_id);

-- ─── catalyst_system_state ───────────────────────────────────────────

CREATE TABLE IF NOT EXISTS catalyst_system_state (
    scan_session        VARCHAR(64) NOT NULL PRIMARY KEY,   -- upsert 幂等键
    lovetrade_id        BIGINT,
    date                DATE NOT NULL,
    scan_time           TIME,
    overall_phase       VARCHAR(20) NOT NULL,               -- stable/oscillation/critical/transition/trending_up/trending_down/news_shock
    overall_note        TEXT,                                -- 不限长（修复 lovetrade 500）
    topic_states        JSONB NOT NULL DEFAULT '{}',         -- 不限键数（修复 lovetrade 7键限）
    global_coupling     VARCHAR(10) DEFAULT 'medium',
    coupling_note       TEXT,
    global_data         JSONB,
    sentiment           VARCHAR(20),                        -- risk_on/risk_off/neutral
    sentiment_indicators JSONB,                              -- 不限长（修复 lovetrade 500）
    evolution_direction VARCHAR(20),
    evolution_note      TEXT,
    source              VARCHAR(64) NOT NULL DEFAULT 'lovetrade-mysql',
    ingest_ts           TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_time        TIMESTAMPTZ,
    updated_time        TIMESTAMPTZ
);
COMMENT ON TABLE catalyst_system_state IS 'D12 系统状态快照（upsert by scan_session，Z7-ext 新建）';

CREATE INDEX IF NOT EXISTS idx_ss_date ON catalyst_system_state(date);
CREATE INDEX IF NOT EXISTS idx_ss_phase ON catalyst_system_state(overall_phase);
CREATE INDEX IF NOT EXISTS idx_ss_lovetrade ON catalyst_system_state(lovetrade_id);

-- ─── 白名单追加（data-api /data/{table} 通用读） ────────────────────
-- 白名单在 main.py META 中维护，此处仅做注释提醒
-- catalyst_impact, catalyst_active_message, catalyst_system_state 已加入 main.py META

-- ─── calibration_view 更新（加入 partial = 0.5） ────────────────────
-- 口径4: partial 计 0.5 hit
DROP VIEW IF EXISTS calibration_view;
CREATE VIEW calibration_view AS
SELECT
    category,
    date_trunc('month', created_at)::date AS "window",
    COUNT(*) AS n,
    AVG(confidence_pct) AS avg_conf_pct,
    (
        SUM(CASE WHEN result = 'hit' THEN 1 WHEN result = 'partial' THEN 0.5 ELSE 0 END)::double precision
        / NULLIF(SUM((result IN ('hit','miss','partial'))::int), 0)::double precision
    ) AS hit_rate,
    AVG(
        power(
            (confidence_pct::numeric / 100.0) - (CASE WHEN result = 'hit' THEN 1 WHEN result = 'partial' THEN 0.5 ELSE 0 END)::numeric,
            2
        )
    ) AS brier
FROM prediction
WHERE result IN ('hit', 'miss', 'partial')
GROUP BY category, date_trunc('month', created_at)::date;

-- ─── base_rate 重跑（partial 纳入） ─────────────────────────────────
-- base_rate 聚合逻辑在 dsched 中，此处仅做视图修正；实际重跑由迁移脚本触发

-- ─── schema_migrations 记账 ─────────────────────────────────────────
INSERT INTO schema_migrations (version, applied_at, checksum, note)
VALUES ('V006', now(), 'z7ext_catalyst_three_tables', '催化雷达三表: impact/active_message/system_state + calibration_view partial 0.5')
ON CONFLICT (version) DO NOTHING;
