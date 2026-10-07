-- V001__hypertables_policies.sql
-- Hypertable creation, compression, retention, views, continuous aggregates
-- Idempotent: uses IF NOT EXISTS and DO blocks
-- Must run AFTER V001__init_d0_d1_d2_d3_d7.sql

-- ==========================================
-- Hypertables (日频 chunk=1年, 分钟 chunk=7天, 新闻 chunk=1月, 管道 chunk=1月)
-- ==========================================

-- D1 指数日K
SELECT create_hypertable('index_daily', 'date',
    chunk_time_interval => INTERVAL '1 year', if_not_exists => true);

-- D2 个股日K
SELECT create_hypertable('stock_daily', 'date',
    chunk_time_interval => INTERVAL '1 year', if_not_exists => true);

-- D2 ETF日K
SELECT create_hypertable('etf_daily', 'date',
    chunk_time_interval => INTERVAL '1 year', if_not_exists => true);

-- D3 竞价列表
SELECT create_hypertable('bidding_list', 'date',
    chunk_time_interval => INTERVAL '1 year', if_not_exists => true);

-- D7 全球日频 (普通表，日频量小)
-- global_daily 量小（21品种×244天≈5124行/年），不转 hypertable

-- ==========================================
-- 压缩策略
-- ==========================================

-- index_daily: 30天后压缩, segmentby code
DO $$ BEGIN
    ALTER TABLE index_daily SET (timescaledb.compress,
        timescaledb.compress_segmentby='code',
        timescaledb.compress_orderby='date DESC');
EXCEPTION WHEN others THEN
    RAISE NOTICE 'index_daily compression already set or error: %', SQLERRM;
END $$;
SELECT add_compression_policy('index_daily', INTERVAL '30 days', if_not_exists => true);

-- stock_daily: 30天后压缩, segmentby code
DO $$ BEGIN
    ALTER TABLE stock_daily SET (timescaledb.compress,
        timescaledb.compress_segmentby='code',
        timescaledb.compress_orderby='date DESC');
EXCEPTION WHEN others THEN
    RAISE NOTICE 'stock_daily compression already set or error: %', SQLERRM;
END $$;
SELECT add_compression_policy('stock_daily', INTERVAL '30 days', if_not_exists => true);

-- etf_daily: 30天后压缩
DO $$ BEGIN
    ALTER TABLE etf_daily SET (timescaledb.compress,
        timescaledb.compress_segmentby='code',
        timescaledb.compress_orderby='date DESC');
EXCEPTION WHEN others THEN
    RAISE NOTICE 'etf_daily compression already set or error: %', SQLERRM;
END $$;
SELECT add_compression_policy('etf_daily', INTERVAL '30 days', if_not_exists => true);

-- bidding_list: 30天后压缩
DO $$ BEGIN
    ALTER TABLE bidding_list SET (timescaledb.compress,
        timescaledb.compress_segmentby='code',
        timescaledb.compress_orderby='date DESC');
EXCEPTION WHEN others THEN
    RAISE NOTICE 'bidding_list compression already set or error: %', SQLERRM;
END $$;
SELECT add_compression_policy('bidding_list', INTERVAL '30 days', if_not_exists => true);

-- ==========================================
-- 管道表: ingest_log / quarantine (hypertable + 保留3年)
-- ==========================================

CREATE TABLE IF NOT EXISTS ingest_log (
  ts               TIMESTAMPTZ NOT NULL DEFAULT now(),
  run_id           BIGINT GENERATED ALWAYS AS IDENTITY,
  job              TEXT NOT NULL,
  trigger          TEXT NOT NULL DEFAULT 'scheduled',
  domain           TEXT,
  target_table     TEXT,
  source_used      TEXT,
  status           TEXT NOT NULL,         -- OK/PARTIAL/FAIL/MISS
  rows_in          INT,
  rows_written     INT,
  rows_quarantined INT,
  verify_diff_max  DOUBLE PRECISION,
  duration_ms      INT,
  note             TEXT,
  ingest_ts        TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (ts, run_id)
);
COMMENT ON TABLE ingest_log IS '管道-采集日志（全链路审计）';

SELECT create_hypertable('ingest_log', 'ts',
    chunk_time_interval => INTERVAL '1 month', if_not_exists => true);
SELECT add_retention_policy('ingest_log', INTERVAL '3 years', if_not_exists => true);

CREATE TABLE IF NOT EXISTS quarantine (
  ts           TIMESTAMPTZ NOT NULL DEFAULT now(),
  q_id         BIGINT GENERATED ALWAYS AS IDENTITY,
  job          TEXT NOT NULL,
  target_table TEXT NOT NULL,
  row_key      TEXT NOT NULL,
  payload      JSONB NOT NULL,
  failed_rules JSONB NOT NULL,
  severity     TEXT NOT NULL DEFAULT 'block',
  status       TEXT NOT NULL DEFAULT 'pending', -- pending/replayed/rejected/fixed
  resolved_at  TIMESTAMPTZ,
  resolved_by  TEXT,
  note         TEXT,
  source       TEXT NOT NULL,
  ingest_ts    TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (ts, q_id)
);
COMMENT ON TABLE quarantine IS '管道-行级隔离区';

SELECT create_hypertable('quarantine', 'ts',
    chunk_time_interval => INTERVAL '1 month', if_not_exists => true);
SELECT add_retention_policy('quarantine', INTERVAL '3 years', if_not_exists => true);

-- ==========================================
-- D12 认知/预测/基率（Z1 建表，Z2 实装写入通道）
-- ==========================================

CREATE TABLE IF NOT EXISTS cognition (
  cognition_id   TEXT NOT NULL,           -- F/C/H/M 前缀编号
  version        INT NOT NULL DEFAULT 1,
  type           TEXT NOT NULL,
  title          TEXT NOT NULL,
  statement      TEXT NOT NULL,
  source         TEXT NOT NULL,
  confidence     DOUBLE PRECISION CHECK (confidence BETWEEN 0 AND 1),
  regime_scope   JSONB,
  validations    JSONB,
  falsifications JSONB,
  derives_from   JSONB,
  status         TEXT NOT NULL DEFAULT 'active',
  actor          TEXT NOT NULL DEFAULT 'guanshi',
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  ingest_ts      TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (cognition_id, version)
);
COMMENT ON TABLE cognition IS 'D12 认知（版本化）';

CREATE TABLE IF NOT EXISTS prediction (
  prediction_id    TEXT PRIMARY KEY,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  statement        TEXT NOT NULL,
  category         TEXT NOT NULL,         -- 地缘/全球/产业/政策/业绩/情绪/资金
  confidence_pct   INT NOT NULL CHECK (confidence_pct BETWEEN 0 AND 100),
  base_rate_ref    TEXT,
  conditions       JSONB,
  falsify          JSONB NOT NULL,
  check_date       DATE NOT NULL,
  regime_at_create TEXT,
  result           TEXT NOT NULL DEFAULT 'pending',
  result_note      TEXT,
  checked_at       TIMESTAMPTZ,
  writeback_done   BOOLEAN NOT NULL DEFAULT false,
  actor            TEXT NOT NULL DEFAULT 'guanshi',
  source           TEXT NOT NULL DEFAULT 'guanshi',
  ingest_ts        TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE prediction IS 'D12 预测';
CREATE INDEX IF NOT EXISTS idx_pred_due ON prediction (check_date, result);

CREATE TABLE IF NOT EXISTS base_rate (
  regime       TEXT NOT NULL,
  category     TEXT NOT NULL,
  horizon      TEXT NOT NULL,
  window_end   DATE NOT NULL,
  window_start DATE,
  n_samples    INT NOT NULL,
  hit_rate     DOUBLE PRECISION,
  avg_ret      DOUBLE PRECISION,
  stat_json    JSONB,
  source       TEXT NOT NULL DEFAULT 'computed',
  ingest_ts    TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (regime, category, horizon, window_end)
);
COMMENT ON TABLE base_rate IS 'D12 基率表（M-005）';

-- ==========================================
-- D12 精细化权限（duser_d12writer 仅限 cognition/prediction/base_rate）
-- ==========================================
GRANT INSERT, UPDATE ON TABLE cognition TO duser_d12writer;
GRANT INSERT, UPDATE ON TABLE prediction TO duser_d12writer;
GRANT INSERT, UPDATE ON TABLE base_rate TO duser_d12writer;

-- ==========================================
-- 视图与连续聚合
-- ==========================================

-- 分钟表（为连续聚合准备）
CREATE TABLE IF NOT EXISTS index_minute (
  ts       TIMESTAMPTZ NOT NULL,
  code     TEXT NOT NULL,
  freq     TEXT NOT NULL DEFAULT '1m',
  open     DOUBLE PRECISION,
  high     DOUBLE PRECISION,
  low      DOUBLE PRECISION,
  close    DOUBLE PRECISION,
  volume   DOUBLE PRECISION,
  amount   DOUBLE PRECISION,
  source   TEXT NOT NULL,
  ingest_ts TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (ts, code, freq)
);
COMMENT ON TABLE index_minute IS 'D1 指数分钟【HT】chunk=7天；保留3年';
SELECT create_hypertable('index_minute', 'ts',
    chunk_time_interval => INTERVAL '7 days', if_not_exists => true);
SELECT add_retention_policy('index_minute', INTERVAL '3 years', if_not_exists => true);

CREATE TABLE IF NOT EXISTS stock_minute (
  ts        TIMESTAMPTZ NOT NULL,
  code      TEXT NOT NULL,
  freq      TEXT NOT NULL DEFAULT '1m',
  price     DOUBLE PRECISION,
  open      DOUBLE PRECISION,
  high      DOUBLE PRECISION,
  low       DOUBLE PRECISION,
  vol       DOUBLE PRECISION,
  amount    DOUBLE PRECISION,
  avg_price DOUBLE PRECISION,
  source    TEXT NOT NULL,
  ingest_ts TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (ts, code, freq)
);
COMMENT ON TABLE stock_minute IS 'D2 个股分钟【HT】chunk=7天；保留3年';
SELECT create_hypertable('stock_minute', 'ts',
    chunk_time_interval => INTERVAL '7 days', if_not_exists => true);
SELECT add_retention_policy('stock_minute', INTERVAL '3 years', if_not_exists => true);

CREATE TABLE IF NOT EXISTS global_minute (
  ts       TIMESTAMPTZ NOT NULL,
  code     TEXT NOT NULL,
  freq     TEXT NOT NULL DEFAULT '15m',
  price    DOUBLE PRECISION,
  pct      DOUBLE PRECISION,
  session  TEXT,
  source   TEXT NOT NULL,
  ingest_ts TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (ts, code, freq)
);
COMMENT ON TABLE global_minute IS 'D7 全球分钟【HT】chunk=7天；保留3年';
SELECT create_hypertable('global_minute', 'ts',
    chunk_time_interval => INTERVAL '7 days', if_not_exists => true);
SELECT add_retention_policy('global_minute', INTERVAL '3 years', if_not_exists => true);

-- 5分钟连续聚合（由 1m 自动生成）
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_class WHERE relname = 'stock_minute_5m') THEN
        CREATE MATERIALIZED VIEW stock_minute_5m
        WITH (timescaledb.continuous) AS
        SELECT time_bucket(INTERVAL '5 minutes', ts) AS ts,
               code,
               '5m' AS freq,
               (first(open, ts)) AS open,
               max(high) AS high,
               min(low) AS low,
               last(price, ts) AS close,
               last(price, ts) AS price,
               sum(vol) AS vol,
               sum(amount) AS amount,
               sum(amount)/NULLIF(sum(vol)*100,0) AS avg_price
        FROM stock_minute
        GROUP BY 1, 2
        WITH NO DATA;

        PERFORM add_continuous_aggregate_policy('stock_minute_5m',
            start_offset => INTERVAL '1 day',
            end_offset => INTERVAL '5 minutes',
            schedule_interval => INTERVAL '15 minutes');
    END IF;
END $$;

-- 校准视图
CREATE OR REPLACE VIEW calibration_view AS
SELECT category,
       date_trunc('month', created_at)::date AS window,
       COUNT(*) AS n,
       AVG(confidence_pct) AS avg_conf_pct,
       SUM((result='hit')::int)::float
         / NULLIF(SUM((result IN ('hit','miss'))::int),0) AS hit_rate,
       AVG(power(confidence_pct/100.0 - (result='hit')::int, 2)) AS brier
FROM prediction
WHERE result IN ('hit','miss')
GROUP BY 1, 2;

-- 分钟→日K互核视图
CREATE OR REPLACE VIEW stock_daily_from_minute AS
SELECT (ts AT TIME ZONE 'Asia/Shanghai')::date AS date, code,
       (first(price, ts)) AS open, max(high) AS high, min(low) AS low,
       last(price, ts) AS close, sum(vol) AS volume, sum(amount) AS amount
FROM stock_minute WHERE freq='1m'
GROUP BY 1, 2;

-- D12 认知当前版本视图
CREATE OR REPLACE VIEW cognition_current AS
SELECT DISTINCT ON (cognition_id) * FROM cognition
ORDER BY cognition_id, version DESC;

-- ==========================================
-- 更新 migration 记录
-- ==========================================
INSERT INTO schema_migrations (version, checksum, note)
VALUES ('V001_ht', md5('V001__hypertables_policies_sql'), 'Hypertables + compression + retention + views + D12')
ON CONFLICT (version) DO NOTHING;
