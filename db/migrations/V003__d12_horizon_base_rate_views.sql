-- V003: D12 horizon 列 + base_rate 表 + calibration_view
-- Z7 · 2026-10-10 · 铸码实装
-- 依据: docs/base_rate_calibration_spec.md v1.0 (观势 2026-10-07 会签冻结)

-- ─── 口径1: prediction 增加 horizon 显式列 ───────────────────────────
ALTER TABLE prediction ADD COLUMN IF NOT EXISTS horizon VARCHAR(4);
COMMENT ON COLUMN prediction.horizon IS '预测窗口: T1/T3/T5/W1 (口径1 观势 2026-10-07 裁决)';

-- ─── base_rate 表 (口径1-5) ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS base_rate (
    regime          VARCHAR(32) NOT NULL,
    category        VARCHAR(16) NOT NULL,
    horizon         VARCHAR(4)  NOT NULL,
    window_type     VARCHAR(16) NOT NULL DEFAULT 'rolling_90',  -- rolling_90 / full
    window_end      DATE        NOT NULL,
    window_start    DATE        NOT NULL,
    n_samples       INT         NOT NULL DEFAULT 0,
    hit_rate        DOUBLE PRECISION,
    stat_json       JSONB       NOT NULL DEFAULT '{}'::jsonb,
    reliability     VARCHAR(8)  NOT NULL DEFAULT 'none',  -- low/medium/high/none
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (regime, category, horizon, window_type, window_end)
);
COMMENT ON TABLE base_rate IS '基率聚合表 · 口径1-5 · docs/base_rate_calibration_spec.md';

-- ─── calibration_view (口径4 · 按月分桶) ─────────────────────────────
DROP VIEW IF EXISTS calibration_view;
CREATE VIEW calibration_view AS
SELECT
    category,
    date_trunc('month', created_at)::date AS window,
    COUNT(*) AS n,
    AVG(confidence_pct) AS avg_conf_pct,
    SUM((result = 'hit')::int)::float
        / NULLIF(SUM((result IN ('hit', 'miss'))::int), 0) AS hit_rate,
    AVG(power(confidence_pct / 100.0 - (result = 'hit')::int, 2)) AS brier
FROM prediction
WHERE result IN ('hit', 'miss')
GROUP BY 1, 2;
COMMENT ON VIEW calibration_view IS '校准视图 · 口径4 · 按月分桶 · Brier Score';
