-- V004: 反思层 reflection 表 + journal 视图 + prediction 增列
-- Z7b · 2026-10-10 · 铸码实装
-- 依据: cognition/README.md §8 + specs/architecture-master.md §7
--       梁总 2026-10-08 指示补环

-- ==========================================
-- 1. reflection 表
-- ==========================================
CREATE TABLE IF NOT EXISTS reflection (
    id              BIGSERIAL PRIMARY KEY,
    decision_id     TEXT NOT NULL REFERENCES prediction(prediction_id),
    closed_at       TIMESTAMPTZ,
    quadrant        TEXT CHECK (quadrant IN ('right_right','right_luck','wrong_right','wrong_wrong')),
    error_stage     TEXT CHECK (error_stage IN ('regime','cognition_ref','data_premise','expression','capability_circle','noise')),
    lesson_text     TEXT,
    lesson_kind     TEXT CHECK (lesson_kind IN ('candidate_cognition','rule_revision','none')),
    action_item     TEXT,
    action_status   TEXT NOT NULL DEFAULT 'open' CHECK (action_status IN ('open','done','waived')),
    actor           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE reflection IS 'D12 反思记录 · 四象限+归因+教训+行动项';

-- ==========================================
-- 2. reflection_journal 视图（近30天 OR action_status=open）
-- ==========================================
DROP VIEW IF EXISTS reflection_journal;
CREATE VIEW reflection_journal AS
SELECT *
FROM reflection
WHERE closed_at >= now() - INTERVAL '30 days'
   OR action_status = 'open'
ORDER BY closed_at DESC;
COMMENT ON VIEW reflection_journal IS '反思日志视图: 近30天 + open行动项';

-- ==========================================
-- 3. prediction 增列 reasoning_trace / alternatives
--    口径注: 观势规格写 prediction.id，实际 PK 列名 = prediction_id
-- ==========================================
ALTER TABLE prediction ADD COLUMN IF NOT EXISTS reasoning_trace JSONB;
ALTER TABLE prediction ADD COLUMN IF NOT EXISTS alternatives JSONB;
COMMENT ON COLUMN prediction.reasoning_trace IS '预测出口必填 · 观势侧写入 · 2026-10-10规格增补';
COMMENT ON COLUMN prediction.alternatives IS '预测出口必填 · 观势侧写入 · 2026-10-10规格增补';

-- ==========================================
-- 4. 权限 (仿 V001/V002 GRANT 风格)
-- ==========================================
-- reader: SELECT on reflection + reflection_journal
GRANT SELECT ON TABLE reflection TO duser_reader;
GRANT SELECT ON reflection_journal TO duser_reader;

-- d12writer: INSERT + SELECT on reflection, USAGE on sequence (POST /reflection 走 get_d12writer_conn)
GRANT INSERT, SELECT ON TABLE reflection TO duser_d12writer;
GRANT USAGE, SELECT ON SEQUENCE reflection_id_seq TO duser_d12writer;

-- ==========================================
-- 5. 登记 schema_migrations
-- ==========================================
INSERT INTO schema_migrations (version, checksum, note)
VALUES ('V004', md5('V004__reflection_layer_sql'), '反思层: reflection表 + journal视图 + prediction增列(reasoning_trace/alternatives)')
ON CONFLICT (version) DO NOTHING;
