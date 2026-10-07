-- V001__init_d0_d1_d2_d3_d7.sql
-- 观势数据层 · 全量 DDL（D0/D1/D2/D3/D7 + 辅助表 + 管道表 + bidding_list）
-- 幂等：所有 CREATE TABLE 使用 IF NOT EXISTS
-- 时区：Asia/Shanghai
-- 审计列：所有表含 source TEXT NOT NULL, ingest_ts TIMESTAMPTZ NOT NULL DEFAULT now()

-- ==========================================
-- 0. schema_migrations (幂等控制)
-- ==========================================
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     TEXT PRIMARY KEY,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    checksum    TEXT,
    note        TEXT
);

-- Skip if already applied
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM schema_migrations WHERE version = 'V001') THEN
        RAISE NOTICE 'V001 already applied, skipping all DDL.';
    END IF;
END $$;

-- ==========================================
-- 0.1 辅助表
-- ==========================================
CREATE TABLE IF NOT EXISTS instrument_master (
  code        TEXT PRIMARY KEY,
  name        TEXT NOT NULL,
  aliases     JSONB,
  market      TEXT NOT NULL,
  inst_type   TEXT NOT NULL,
  board       TEXT,
  list_date   DATE,
  delist_date DATE,
  status      TEXT NOT NULL DEFAULT 'active',
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  source      TEXT NOT NULL,
  ingest_ts   TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE instrument_master IS '证券主档（全量 code 字典；旧码/别名映射）';

CREATE TABLE IF NOT EXISTS watchlist (
  code        TEXT PRIMARY KEY,
  name        TEXT,
  added_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  reason      TEXT,
  active      BOOLEAN NOT NULL DEFAULT true,
  source      TEXT NOT NULL DEFAULT 'guanshi',
  ingest_ts   TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE watchlist IS '分钟采集观察池（上限 200 只）';

-- ==========================================
-- D0 日历
-- ==========================================
CREATE TABLE IF NOT EXISTS trade_cal (
  market         TEXT   NOT NULL,
  cal_date       DATE   NOT NULL,
  is_open        SMALLINT NOT NULL,
  prev_open_date DATE,
  note           TEXT,
  source         TEXT   NOT NULL,
  ingest_ts      TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (market, cal_date)
);
COMMENT ON TABLE trade_cal IS 'D0 交易日历';

CREATE TABLE IF NOT EXISTS session_def (
  market         TEXT NOT NULL,
  session        TEXT NOT NULL,
  start_time     TIME NOT NULL,
  end_time       TIME NOT NULL,
  tz             TEXT NOT NULL DEFAULT 'Asia/Shanghai',
  effective_from DATE NOT NULL,
  effective_to   DATE,
  source         TEXT NOT NULL,
  ingest_ts      TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (market, session, effective_from)
);
COMMENT ON TABLE session_def IS 'D0 交易时段定义';

-- ==========================================
-- D1 行情-指数
-- ==========================================
CREATE TABLE IF NOT EXISTS index_daily (
  date          DATE NOT NULL,
  code          TEXT NOT NULL,
  name          TEXT,
  open          DOUBLE PRECISION,
  high          DOUBLE PRECISION,
  low           DOUBLE PRECISION,
  close         DOUBLE PRECISION NOT NULL,
  pct           DOUBLE PRECISION,
  volume        DOUBLE PRECISION,
  amount        DOUBLE PRECISION,
  turnover_rate DOUBLE PRECISION,
  verify_source TEXT,
  verify_diff   DOUBLE PRECISION,
  source        TEXT NOT NULL,
  ingest_ts     TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (date, code)
);
COMMENT ON TABLE index_daily IS 'D1 指数日K【HT】chunk=1年；压缩30d后(segmentby code)；全留';

-- ==========================================
-- D2 行情-个股
-- ==========================================
CREATE TABLE IF NOT EXISTS stock_daily (
  date          DATE NOT NULL,
  code          TEXT NOT NULL,
  name          TEXT,
  open          DOUBLE PRECISION NOT NULL,
  high          DOUBLE PRECISION NOT NULL,
  low           DOUBLE PRECISION NOT NULL,
  close         DOUBLE PRECISION NOT NULL,
  pct           DOUBLE PRECISION,
  volume        DOUBLE PRECISION,
  amount        DOUBLE PRECISION,
  turnover_rate DOUBLE PRECISION,
  total_mv      DOUBLE PRECISION,
  circ_mv       DOUBLE PRECISION,
  pe_ttm        DOUBLE PRECISION,
  pb            DOUBLE PRECISION,
  adj_factor    DOUBLE PRECISION,
  is_st         BOOLEAN NOT NULL DEFAULT false,
  is_suspended  BOOLEAN NOT NULL DEFAULT false,
  verify_source TEXT,
  verify_diff   DOUBLE PRECISION,
  source        TEXT NOT NULL,
  ingest_ts     TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (date, code)
);
COMMENT ON TABLE stock_daily IS 'D2 个股日K【HT】chunk=1年；压缩30d后(segmentby code)；全留';

CREATE TABLE IF NOT EXISTS etf_daily (
  date         DATE NOT NULL,
  code         TEXT NOT NULL,
  name         TEXT,
  open         DOUBLE PRECISION,
  high         DOUBLE PRECISION,
  low          DOUBLE PRECISION,
  close        DOUBLE PRECISION NOT NULL,
  pct          DOUBLE PRECISION,
  volume       DOUBLE PRECISION,
  amount       DOUBLE PRECISION,
  nav          DOUBLE PRECISION,
  premium_rate DOUBLE PRECISION,
  source       TEXT NOT NULL,
  ingest_ts    TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (date, code)
);
COMMENT ON TABLE etf_daily IS 'D2 ETF日K【HT】chunk=1年；压缩30d后；全留';

-- ==========================================
-- D3 情绪打板
-- ==========================================
CREATE TABLE IF NOT EXISTS zt_pool (
  date           DATE NOT NULL,
  code           TEXT NOT NULL,
  name           TEXT,
  close          DOUBLE PRECISION,
  pct            DOUBLE PRECISION,
  amount         DOUBLE PRECISION,
  circ_mv        DOUBLE PRECISION,
  turnover_rate  DOUBLE PRECISION,
  seal_amount    DOUBLE PRECISION,
  first_seal_time TIME,
  last_seal_time  TIME,
  break_times    INT,
  up_days        INT,
  board_days     INT,
  industry       TEXT,
  theme          TEXT,
  reason         TEXT,
  snapshot_flag  BOOLEAN NOT NULL DEFAULT false,
  source         TEXT NOT NULL,
  ingest_ts      TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (date, code)
);
COMMENT ON TABLE zt_pool IS 'D3 涨停池';

CREATE TABLE IF NOT EXISTS zb_pool (
  date          DATE NOT NULL,
  code          TEXT NOT NULL,
  name          TEXT,
  close         DOUBLE PRECISION,
  pct           DOUBLE PRECISION,
  high          DOUBLE PRECISION,
  amount        DOUBLE PRECISION,
  circ_mv       DOUBLE PRECISION,
  turnover_rate DOUBLE PRECISION,
  first_seal_time TIME,
  break_times   INT,
  up_days       INT,
  board_days    INT,
  industry      TEXT,
  source        TEXT NOT NULL,
  ingest_ts     TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (date, code)
);
COMMENT ON TABLE zb_pool IS 'D3 炸板池';

CREATE TABLE IF NOT EXISTS dt_pool (
  date           DATE NOT NULL,
  code           TEXT NOT NULL,
  name           TEXT,
  close          DOUBLE PRECISION,
  pct            DOUBLE PRECISION,
  amount         DOUBLE PRECISION,
  circ_mv        DOUBLE PRECISION,
  turnover_rate  DOUBLE PRECISION,
  seal_amount    DOUBLE PRECISION,
  first_seal_time TIME,
  last_seal_time  TIME,
  break_times    INT,
  board_days     INT,
  industry       TEXT,
  source         TEXT NOT NULL,
  ingest_ts      TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (date, code)
);
COMMENT ON TABLE dt_pool IS 'D3 跌停池';

CREATE TABLE IF NOT EXISTS yzt_pool (
  date          DATE NOT NULL,
  code          TEXT NOT NULL,
  name          TEXT,
  close         DOUBLE PRECISION,
  pct           DOUBLE PRECISION,
  amount        DOUBLE PRECISION,
  circ_mv       DOUBLE PRECISION,
  turnover_rate DOUBLE PRECISION,
  prev_seal_amount DOUBLE PRECISION,
  prev_board_days  INT,
  industry      TEXT,
  source        TEXT NOT NULL,
  ingest_ts     TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (date, code)
);
COMMENT ON TABLE yzt_pool IS 'D3 昨日涨停今日表现池';

CREATE TABLE IF NOT EXISTS sentiment_daily (
  date            DATE PRIMARY KEY,
  limit_up        INT,
  limit_down      INT,
  seal_rate       DOUBLE PRECISION,
  broken_rate     DOUBLE PRECISION,
  max_board       INT,
  board_ladder    JSONB,
  promote_rate    DOUBLE PRECISION,
  up_cnt          INT,
  down_cnt        INT,
  flat_cnt        INT,
  dbcgl           DOUBLE PRECISION,
  dbyll           DOUBLE PRECISION,
  yest_rase       DOUBLE PRECISION,
  sentiment_score DOUBLE PRECISION,
  zt_detail       JSONB,
  verify_source   TEXT,
  verify_diff     DOUBLE PRECISION,
  source          TEXT NOT NULL DEFAULT 'computed',
  ingest_ts       TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE sentiment_daily IS 'D3 市场情绪日度汇总';

-- ==========================================
-- D7 全球
-- ==========================================
CREATE TABLE IF NOT EXISTS global_daily (
  date          DATE NOT NULL,
  market        TEXT NOT NULL,
  code          TEXT NOT NULL,
  name          TEXT,
  session       TEXT NOT NULL DEFAULT 'close',
  open          DOUBLE PRECISION,
  high          DOUBLE PRECISION,
  low           DOUBLE PRECISION,
  close         DOUBLE PRECISION NOT NULL,
  pct           DOUBLE PRECISION,
  volume        DOUBLE PRECISION,
  amount        DOUBLE PRECISION,
  verify_source TEXT,
  verify_diff   DOUBLE PRECISION,
  source        TEXT NOT NULL,
  ingest_ts     TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (date, code, session)
);
COMMENT ON TABLE global_daily IS 'D7 全球品种日频（21项）';

-- ==========================================
-- 管道表
-- ==========================================
CREATE TABLE IF NOT EXISTS job_registry (
  job_name      TEXT PRIMARY KEY,
  domain        TEXT NOT NULL,
  target_tables TEXT[] NOT NULL,
  schedule_cron TEXT,
  source_chain  JSONB NOT NULL,
  rate_limit    JSONB,
  retry_policy  JSONB NOT NULL DEFAULT '{"tries":3,"backoff_s":[5,30,120]}',
  timeout_s     INT NOT NULL DEFAULT 600,
  critical      BOOLEAN NOT NULL DEFAULT false,
  enabled       BOOLEAN NOT NULL DEFAULT true,
  owner         TEXT NOT NULL DEFAULT 'zhuma',
  note          TEXT,
  source        TEXT NOT NULL DEFAULT 'config',
  ingest_ts     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE job_registry IS '调度注册表 = 唯一调度事实源';

CREATE TABLE IF NOT EXISTS verify_source (
  date          DATE NOT NULL,
  target_table  TEXT NOT NULL,
  code          TEXT NOT NULL,
  primary_source TEXT NOT NULL,
  primary_value  DOUBLE PRECISION,
  verify_source  TEXT NOT NULL,
  verify_value   DOUBLE PRECISION,
  diff_pct       DOUBLE PRECISION,
  source        TEXT NOT NULL DEFAULT 'verify',
  ingest_ts     TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (date, target_table, code, verify_source)
);
COMMENT ON TABLE verify_source IS '双源复核明细';

CREATE TABLE IF NOT EXISTS verify_diff (
  date          DATE NOT NULL,
  target_table  TEXT NOT NULL,
  total_rows    INT,
  checked_rows  INT,
  warn_count    INT,
  block_count   INT,
  max_diff_pct  DOUBLE PRECISION,
  source        TEXT NOT NULL DEFAULT 'verify',
  ingest_ts     TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (date, target_table)
);
COMMENT ON TABLE verify_diff IS '双源复核汇总';

-- ==========================================
-- bidding_list (§11.5)
-- ==========================================
CREATE TABLE IF NOT EXISTS bidding_list (
  date          DATE NOT NULL,
  code          TEXT NOT NULL,
  name          TEXT,
  jjzf          DOUBLE PRECISION,
  jjje          BIGINT,
  jjcje         BIGINT,
  jjhs          DOUBLE PRECISION,
  ztwme         BIGINT,
  twenty_ztwme  BIGINT,
  fd            BIGINT,
  zdfd          BIGINT,
  sjlt          BIGINT,
  ssbk          TEXT,
  ztsj          TEXT,
  ztyy          TEXT,
  bkztsl        INT,
  limit_up_status TEXT,
  quotations_type SMALLINT NOT NULL DEFAULT 1,
  source        TEXT NOT NULL,
  ingest_ts     TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (date, code, quotations_type)
);
COMMENT ON TABLE bidding_list IS 'D3 竞价列表（五维原料）';

-- ==========================================
-- 记录 migration
-- ==========================================
INSERT INTO schema_migrations (version, checksum, note)
VALUES ('V001', md5('V001__init_d0_d1_d2_d3_d7_sql'), 'D0/D1/D2/D3/D7 + 辅助 + 管道 + bidding_list')
ON CONFLICT (version) DO NOTHING;
