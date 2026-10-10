-- V004: 反思层 reflection 表 + journal 视图 + prediction 增列 + regime_daily + job_registry.config
-- Z7b + Z7c · 2026-10-10 · 铸码实装
-- 依据: cognition/README.md §8 + specs/architecture-master.md §7/§8.8
--       梁总 2026-10-08 指示补环 + 2026-10-10 指示"反思必须基于数据层数据"
-- 口径注: 观势规格写 prediction.id，实际 PK 列名 = prediction_id

-- ==========================================
-- 1. reflection 表 (Z7b 基础 + Z7c evidence 两列)
-- ==========================================
CREATE TABLE IF NOT EXISTS reflection (
    id                BIGSERIAL PRIMARY KEY,
    decision_id       TEXT NOT NULL REFERENCES prediction(prediction_id),
    closed_at         TIMESTAMPTZ,
    quadrant          TEXT CHECK (quadrant IN ('right_right','right_luck','wrong_right','wrong_wrong')),
    error_stage       TEXT CHECK (error_stage IN ('regime','cognition_ref','data_premise','expression','capability_circle','noise')),
    lesson_text       TEXT,
    lesson_kind       TEXT CHECK (lesson_kind IN ('candidate_cognition','rule_revision','none')),
    action_item       TEXT,
    action_status     TEXT NOT NULL DEFAULT 'open' CHECK (action_status IN ('open','done','waived')),
    evidence_refs     JSONB,
    evidence_summary  TEXT,
    actor             TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE reflection IS 'D12 反思记录 · 四象限+归因+教训+行动项+证据包';

-- 索引
CREATE INDEX IF NOT EXISTS idx_reflection_decision_id ON reflection(decision_id);
CREATE INDEX IF NOT EXISTS idx_reflection_closed_at ON reflection(closed_at DESC);
CREATE INDEX IF NOT EXISTS idx_reflection_action_status ON reflection(action_status);

-- ==========================================
-- 2. reflection_journal 视图（近30天 OR action_status=open）
-- ==========================================
DROP VIEW IF EXISTS reflection_journal;
CREATE VIEW reflection_journal AS
SELECT id, decision_id, closed_at, quadrant, error_stage, lesson_text, lesson_kind,
       action_item, action_status, evidence_refs, evidence_summary, actor, created_at
FROM reflection
WHERE closed_at >= now() - INTERVAL '30 days'
   OR action_status = 'open'
ORDER BY closed_at DESC;
COMMENT ON VIEW reflection_journal IS '反思日志视图: 近30天 + open行动项 (含evidence)';

-- ==========================================
-- 3. prediction 增列 reasoning_trace / alternatives
-- ==========================================
ALTER TABLE prediction ADD COLUMN IF NOT EXISTS reasoning_trace JSONB;
ALTER TABLE prediction ADD COLUMN IF NOT EXISTS alternatives JSONB;
COMMENT ON COLUMN prediction.reasoning_trace IS '预测出口必填 · 观势侧写入 · 2026-10-10规格增补';
COMMENT ON COLUMN prediction.alternatives IS '预测出口必填 · 观势侧写入 · 2026-10-10规格增补';

-- ==========================================
-- 4. job_registry 增列 config (通用 per-job 配置位, 本波放 route_map)
-- ==========================================
ALTER TABLE job_registry ADD COLUMN IF NOT EXISTS config JSONB;

-- ==========================================
-- 5. regime_daily 表 (Z7c: 相态日序列唯一可查源)
--    理由: prediction.regime_at_create 现 329 行全空, regime 日序列在库里无家
-- ==========================================
CREATE TABLE IF NOT EXISTS regime_daily (
    date        DATE PRIMARY KEY,
    regime      TEXT,
    sub_regime  TEXT,
    quadrant    JSONB,
    evidence    JSONB,
    actor       TEXT,
    source      TEXT,
    ingest_ts   TIMESTAMPTZ DEFAULT now()
);
COMMENT ON TABLE regime_daily IS '相态日序列唯一可查源; 观势每日17:30作业写入; 证据包S3归因用';

-- ==========================================
-- 6. 权限 (仿 V001/V002 GRANT 风格)
-- ==========================================
-- reader: SELECT on reflection/reflection_journal/regime_daily
GRANT SELECT ON TABLE reflection TO duser_reader;
GRANT SELECT ON reflection_journal TO duser_reader;
GRANT SELECT ON TABLE regime_daily TO duser_reader;

-- d12writer: INSERT + SELECT on reflection + regime_daily, USAGE on sequences
GRANT INSERT, SELECT ON TABLE reflection TO duser_d12writer;
GRANT USAGE, SELECT ON SEQUENCE reflection_id_seq TO duser_d12writer;
GRANT INSERT, SELECT ON TABLE regime_daily TO duser_d12writer;

-- d12writer: UPDATE config on job_registry (for route_map PATCH)
GRANT UPDATE (config, updated_at) ON TABLE job_registry TO duser_d12writer;
GRANT SELECT ON TABLE job_registry TO duser_d12writer;

-- ==========================================
-- 7. 登记 schema_migrations
-- ==========================================
INSERT INTO schema_migrations (version, checksum, note)
VALUES ('V004', md5('V004__reflection_layer_sql'),
        '反思层: reflection表+evidence两列+journal视图+prediction留痕+job_registry.config+regime_daily')
ON CONFLICT (version) DO UPDATE SET note = EXCLUDED.note;
