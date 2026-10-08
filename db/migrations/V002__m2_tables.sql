-- V002__m2_tables.sql
-- M2 域表补齐：D4/D5/D6/D9/D10/D11 + radar_event + news
-- 幂等：所有 CREATE TABLE 使用 IF NOT EXISTS

-- ==========================================
-- D4 资金面
-- ==========================================
CREATE TABLE IF NOT EXISTS fund_flow_stock (
  date            DATE NOT NULL,
  code            TEXT NOT NULL,
  name            TEXT,
  close           DOUBLE PRECISION,
  pct             DOUBLE PRECISION,
  main_net_inflow DOUBLE PRECISION,
  main_net_pct    DOUBLE PRECISION,
  super_large_net DOUBLE PRECISION,
  large_net       DOUBLE PRECISION,
  medium_net      DOUBLE PRECISION,
  small_net       DOUBLE PRECISION,
  source          TEXT NOT NULL,
  ingest_ts       TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (date, code)
);
COMMENT ON TABLE fund_flow_stock IS 'D4 个股资金流【HT】chunk=1年';

CREATE TABLE IF NOT EXISTS fund_flow_sector (
  date            DATE NOT NULL,
  sector_code     TEXT NOT NULL,
  sector_name     TEXT,
  kind            TEXT NOT NULL,
  pct             DOUBLE PRECISION,
  main_net_inflow DOUBLE PRECISION,
  main_net_pct    DOUBLE PRECISION,
  lead_stock_code TEXT,
  lead_stock_name TEXT,
  turnover        DOUBLE PRECISION,
  source          TEXT NOT NULL,
  ingest_ts       TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (date, sector_code)
);
COMMENT ON TABLE fund_flow_sector IS 'D4 板块资金流【HT】chunk=1年';

CREATE TABLE IF NOT EXISTS northbound_daily (
  date          DATE PRIMARY KEY,
  hgt_net       DOUBLE PRECISION,
  sgt_net       DOUBLE PRECISION,
  total_net     DOUBLE PRECISION,
  hgt_buy       DOUBLE PRECISION,
  hgt_sell      DOUBLE PRECISION,
  sgt_buy       DOUBLE PRECISION,
  sgt_sell      DOUBLE PRECISION,
  verify_source TEXT,
  verify_diff   DOUBLE PRECISION,
  source        TEXT NOT NULL DEFAULT 'hkex',
  ingest_ts     TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE northbound_daily IS 'D4 北向资金日频';

CREATE TABLE IF NOT EXISTS margin_daily (
  date         DATE PRIMARY KEY,
  margin_bal   DOUBLE PRECISION,
  margin_buy   DOUBLE PRECISION,
  margin_repay DOUBLE PRECISION,
  net_buy      DOUBLE PRECISION,
  short_bal    DOUBLE PRECISION,
  short_vol    DOUBLE PRECISION,
  source       TEXT NOT NULL,
  ingest_ts    TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE margin_daily IS 'D4 两融全市场日频';

CREATE TABLE IF NOT EXISTS margin_stock (
  date         DATE NOT NULL,
  code         TEXT NOT NULL,
  margin_bal   DOUBLE PRECISION,
  margin_buy   DOUBLE PRECISION,
  margin_repay DOUBLE PRECISION,
  short_bal    DOUBLE PRECISION,
  short_vol    DOUBLE PRECISION,
  net_buy      DOUBLE PRECISION,
  source       TEXT NOT NULL,
  ingest_ts    TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (date, code)
);
COMMENT ON TABLE margin_stock IS 'D4 两融标的【HT】chunk=1年';

CREATE TABLE IF NOT EXISTS block_trade (
  date        DATE NOT NULL,
  block_seq   BIGINT GENERATED ALWAYS AS IDENTITY,
  code        TEXT NOT NULL,
  name        TEXT,
  deal_price  DOUBLE PRECISION,
  close_price DOUBLE PRECISION,
  premium_pct DOUBLE PRECISION,
  volume      DOUBLE PRECISION,
  amount      DOUBLE PRECISION,
  buyer       TEXT,
  seller      TEXT,
  source      TEXT NOT NULL,
  ingest_ts   TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (date, block_seq)
);
COMMENT ON TABLE block_trade IS 'D4 大宗交易';

CREATE TABLE IF NOT EXISTS dragon_tiger (
  date        DATE NOT NULL,
  code        TEXT NOT NULL,
  name        TEXT,
  close       DOUBLE PRECISION,
  pct         DOUBLE PRECISION,
  reason      TEXT NOT NULL,
  turnover_rate DOUBLE PRECISION,
  amount      DOUBLE PRECISION,
  circ_mv     DOUBLE PRECISION,
  net_buy     DOUBLE PRECISION,
  buy_amount  DOUBLE PRECISION,
  sell_amount DOUBLE PRECISION,
  buy_top5    JSONB,
  sell_top5   JSONB,
  inst_flag   BOOLEAN,
  inst_net    DOUBLE PRECISION,
  source      TEXT NOT NULL,
  ingest_ts   TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (date, code, LEFT(reason, 100))
);
COMMENT ON TABLE dragon_tiger IS 'D4 龙虎榜';

-- ==========================================
-- D5 筹码股东
-- ==========================================
CREATE TABLE IF NOT EXISTS holder_num (
  code            TEXT NOT NULL,
  date            DATE NOT NULL,
  announce_date   DATE NOT NULL,
  holder_num      INT,
  holder_num_chg  INT,
  holder_num_chg_pct DOUBLE PRECISION,
  avg_hold_num    DOUBLE PRECISION,
  avg_circ_mv     DOUBLE PRECISION,
  source          TEXT NOT NULL,
  ingest_ts       TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (code, date, announce_date)
);
COMMENT ON TABLE holder_num IS 'D5 股东户数';

CREATE TABLE IF NOT EXISTS lockup_calendar (
  unlock_date   DATE NOT NULL,
  code          TEXT NOT NULL,
  name          TEXT,
  unlock_shares DOUBLE PRECISION,
  unlock_mv     DOUBLE PRECISION,
  unlock_pct    DOUBLE PRECISION,
  lock_type     TEXT NOT NULL,
  announce_date DATE,
  source        TEXT NOT NULL,
  ingest_ts     TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (unlock_date, code, lock_type)
);
COMMENT ON TABLE lockup_calendar IS 'D5 解禁日历';

CREATE TABLE IF NOT EXISTS dividend (
  code          TEXT NOT NULL,
  report_period TEXT NOT NULL,
  announce_date DATE NOT NULL,
  plan          TEXT,
  cash_div_tax  DOUBLE PRECISION,
  stock_div     DOUBLE PRECISION,
  transfer      DOUBLE PRECISION,
  record_date   DATE,
  ex_date       DATE,
  pay_date      DATE,
  div_yield     DOUBLE PRECISION,
  progress      TEXT NOT NULL DEFAULT 'plan',
  source        TEXT NOT NULL,
  ingest_ts     TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (code, report_period, announce_date, progress)
);
COMMENT ON TABLE dividend IS 'D5 分红送转';

CREATE TABLE IF NOT EXISTS share_structure (
  date           DATE NOT NULL,
  code           TEXT NOT NULL,
  total_shares   DOUBLE PRECISION,
  circ_shares    DOUBLE PRECISION,
  limited_shares DOUBLE PRECISION,
  detail         JSONB,
  source         TEXT NOT NULL,
  ingest_ts      TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (date, code)
);
COMMENT ON TABLE share_structure IS 'D5 股本结构';

-- ==========================================
-- D6 板块题材
-- ==========================================
CREATE TABLE IF NOT EXISTS sector_daily (
  date            DATE NOT NULL,
  sector_code     TEXT NOT NULL,
  sector_name     TEXT,
  kind            TEXT NOT NULL,
  pct             DOUBLE PRECISION,
  close           DOUBLE PRECISION,
  main_net_inflow DOUBLE PRECISION,
  turnover        DOUBLE PRECISION,
  up_cnt          INT,
  down_cnt        INT,
  lead_stocks     JSONB,
  source          TEXT NOT NULL,
  ingest_ts       TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (date, sector_code)
);
COMMENT ON TABLE sector_daily IS 'D6 板块日行情【HT】chunk=1年';

CREATE TABLE IF NOT EXISTS stock_sector_map (
  code           TEXT NOT NULL,
  sector_code    TEXT NOT NULL,
  sector_name    TEXT,
  kind           TEXT NOT NULL,
  effective_from DATE NOT NULL,
  effective_to   DATE,
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  source         TEXT NOT NULL,
  ingest_ts      TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (code, sector_code, kind, effective_from)
);
COMMENT ON TABLE stock_sector_map IS 'D6 个股↔板块映射（SCD2）';

CREATE TABLE IF NOT EXISTS theme_heat (
  date        DATE NOT NULL,
  item_kind   TEXT NOT NULL,
  item_code   TEXT NOT NULL,
  item_name   TEXT,
  rank        INT,
  heat_score  DOUBLE PRECISION,
  concept_hits JSONB,
  extra       JSONB,
  source      TEXT NOT NULL,
  ingest_ts   TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (date, item_kind, item_code, source)
);
COMMENT ON TABLE theme_heat IS 'D6 题材热度';

-- ==========================================
-- D8 宏观
-- ==========================================
CREATE TABLE IF NOT EXISTS macro_indicators (
  release_date DATE NOT NULL,
  period       TEXT NOT NULL,
  indicator    TEXT NOT NULL,
  country      TEXT NOT NULL DEFAULT 'CN',
  value        DOUBLE PRECISION,
  yoy          DOUBLE PRECISION,
  mom          DOUBLE PRECISION,
  unit         TEXT,
  forecast     DOUBLE PRECISION,
  prev_value   DOUBLE PRECISION,
  source       TEXT NOT NULL,
  ingest_ts    TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (release_date, country, indicator, period)
);
COMMENT ON TABLE macro_indicators IS 'D8 宏观指标';

CREATE TABLE IF NOT EXISTS policy_calendar (
  cal_id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  cal_date       DATE NOT NULL,
  event          TEXT NOT NULL,
  level          TEXT NOT NULL,
  category       TEXT,
  expected_impact TEXT,
  related_codes  JSONB,
  status         TEXT NOT NULL DEFAULT 'scheduled',
  source         TEXT NOT NULL,
  ingest_ts      TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE policy_calendar IS 'D8 政策日历';

CREATE TABLE IF NOT EXISTS earnings_calendar (
  pre_date    DATE NOT NULL,
  code        TEXT NOT NULL,
  name        TEXT,
  report_period TEXT NOT NULL,
  report_type TEXT NOT NULL,
  actual_date DATE,
  status      TEXT NOT NULL DEFAULT 'scheduled',
  source      TEXT NOT NULL,
  ingest_ts   TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (pre_date, code, report_period)
);
COMMENT ON TABLE earnings_calendar IS 'D8 财报披露日历';

-- ==========================================
-- D9 基本面
-- ==========================================
CREATE TABLE IF NOT EXISTS financial_reports (
  announce_date DATE NOT NULL,
  code          TEXT NOT NULL,
  report_period TEXT NOT NULL,
  revenue       DOUBLE PRECISION,
  revenue_yoy   DOUBLE PRECISION,
  net_profit    DOUBLE PRECISION,
  net_profit_yoy DOUBLE PRECISION,
  deduct_profit DOUBLE PRECISION,
  eps           DOUBLE PRECISION,
  roe           DOUBLE PRECISION,
  gross_margin  DOUBLE PRECISION,
  net_margin    DOUBLE PRECISION,
  debt_ratio    DOUBLE PRECISION,
  oper_cashflow DOUBLE PRECISION,
  balance_json  JSONB,
  income_json   JSONB,
  cashflow_json JSONB,
  source        TEXT NOT NULL,
  ingest_ts     TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (announce_date, code, report_period)
);
COMMENT ON TABLE financial_reports IS 'D9 财报';

CREATE TABLE IF NOT EXISTS finance_snapshot (
  date         DATE NOT NULL,
  code         TEXT NOT NULL,
  metrics      JSONB NOT NULL,
  roe          DOUBLE PRECISION,
  gross_margin DOUBLE PRECISION,
  net_margin   DOUBLE PRECISION,
  debt_ratio   DOUBLE PRECISION,
  revenue_yoy  DOUBLE PRECISION,
  net_profit_yoy DOUBLE PRECISION,
  eps          DOUBLE PRECISION,
  bps          DOUBLE PRECISION,
  ocf_ps       DOUBLE PRECISION,
  source       TEXT NOT NULL DEFAULT 'mootdx',
  ingest_ts    TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (date, code)
);
COMMENT ON TABLE finance_snapshot IS 'D9 F10财务快照';

CREATE TABLE IF NOT EXISTS valuation_daily (
  date           DATE NOT NULL,
  code           TEXT NOT NULL,
  pe_ttm         DOUBLE PRECISION,
  pe_static      DOUBLE PRECISION,
  pb             DOUBLE PRECISION,
  ps_ttm         DOUBLE PRECISION,
  pcf_ocf_ttm    DOUBLE PRECISION,
  peg            DOUBLE PRECISION,
  dividend_yield DOUBLE PRECISION,
  total_mv       DOUBLE PRECISION,
  circ_mv        DOUBLE PRECISION,
  source         TEXT NOT NULL,
  ingest_ts      TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (date, code)
);
COMMENT ON TABLE valuation_daily IS 'D9 估值日频【HT】chunk=1年';

-- ==========================================
-- D10 新闻消息
-- ==========================================
CREATE TABLE IF NOT EXISTS news_telegraph (
  pub_ts         TIMESTAMPTZ NOT NULL,
  news_id        TEXT NOT NULL,
  media          TEXT NOT NULL,
  title          TEXT,
  content        TEXT,
  level          TEXT,
  related_codes  JSONB,
  url            TEXT,
  source         TEXT NOT NULL,
  ingest_ts      TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (pub_ts, news_id)
);
COMMENT ON TABLE news_telegraph IS 'D10 新闻电报【HT】chunk=1月';

CREATE TABLE IF NOT EXISTS stock_news (
  pub_ts    TIMESTAMPTZ NOT NULL,
  news_id   TEXT NOT NULL,
  code      TEXT NOT NULL,
  title     TEXT,
  content   TEXT,
  url       TEXT,
  media     TEXT,
  source    TEXT NOT NULL,
  ingest_ts TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (pub_ts, news_id, code)
);
COMMENT ON TABLE stock_news IS 'D10 个股新闻【HT】chunk=1月';

CREATE TABLE IF NOT EXISTS announcements (
  ann_date       DATE NOT NULL,
  ann_id         TEXT NOT NULL,
  code           TEXT NOT NULL,
  name           TEXT,
  title          TEXT NOT NULL,
  ann_type       TEXT,
  url            TEXT,
  pdf_local_path TEXT,
  source         TEXT NOT NULL DEFAULT 'cninfo',
  ingest_ts      TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (ann_date, ann_id)
);
COMMENT ON TABLE announcements IS 'D10 公告【HT】chunk=1月';

CREATE TABLE IF NOT EXISTS market_messages (
  msg_ts        TIMESTAMPTZ NOT NULL,
  msg_id        TEXT NOT NULL,
  channel       TEXT,
  code          TEXT,
  title         TEXT,
  content       TEXT,
  catalyst_type TEXT,
  strength      DOUBLE PRECISION,
  url           TEXT,
  source        TEXT NOT NULL,
  ingest_ts     TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (msg_ts, msg_id)
);
COMMENT ON TABLE market_messages IS 'D10 lovetrade消息流【HT】chunk=1月';

-- ==========================================
-- D11 衍生品
-- ==========================================
CREATE TABLE IF NOT EXISTS option_contracts (
  contract_id    TEXT PRIMARY KEY,
  underlying_code TEXT NOT NULL,
  exchange       TEXT NOT NULL,
  option_type    TEXT NOT NULL,
  exercise_type  TEXT,
  strike         DOUBLE PRECISION NOT NULL,
  contract_unit  INT,
  list_date      DATE,
  expire_date    DATE NOT NULL,
  delist_date    DATE,
  status         TEXT NOT NULL DEFAULT 'listed',
  source         TEXT NOT NULL,
  ingest_ts      TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE option_contracts IS 'D11 期权合约主档';

CREATE TABLE IF NOT EXISTS option_tquote (
  date          DATE NOT NULL,
  contract_id   TEXT NOT NULL,
  underlying_code TEXT NOT NULL,
  open          DOUBLE PRECISION,
  high          DOUBLE PRECISION,
  low           DOUBLE PRECISION,
  close         DOUBLE PRECISION,
  settle        DOUBLE PRECISION,
  prev_settle   DOUBLE PRECISION,
  prev_close    DOUBLE PRECISION,
  volume        DOUBLE PRECISION,
  amount        DOUBLE PRECISION,
  open_interest DOUBLE PRECISION,
  source        TEXT NOT NULL DEFAULT 'sina',
  ingest_ts     TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (date, contract_id)
);
COMMENT ON TABLE option_tquote IS 'D11 期权日行情【HT】chunk=1月';

CREATE TABLE IF NOT EXISTS option_greeks_iv (
  date        DATE NOT NULL,
  contract_id TEXT NOT NULL,
  iv          DOUBLE PRECISION,
  delta       DOUBLE PRECISION,
  gamma       DOUBLE PRECISION,
  theta       DOUBLE PRECISION,
  vega        DOUBLE PRECISION,
  rho         DOUBLE PRECISION,
  source      TEXT NOT NULL DEFAULT 'sina',
  ingest_ts   TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (date, contract_id)
);
COMMENT ON TABLE option_greeks_iv IS 'D11 期权Greeks【HT】chunk=1月';

-- ==========================================
-- D3 雷达事件（独立表，§10-Q13）
-- ==========================================
CREATE TABLE IF NOT EXISTS radar_event (
  ts           TIMESTAMPTZ NOT NULL,
  event_id     TEXT NOT NULL,
  event_type   TEXT,
  title        TEXT,
  content      TEXT,
  related_codes JSONB,
  strength     DOUBLE PRECISION,
  extra        JSONB,
  source       TEXT NOT NULL,
  ingest_ts    TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (ts, event_id)
);
COMMENT ON TABLE radar_event IS 'D3 雷达事件流【HT】chunk=7天';

-- ==========================================
-- Hypertables for new tables
-- ==========================================
SELECT create_hypertable('fund_flow_stock', 'date', chunk_time_interval => INTERVAL '1 year', if_not_exists => true);
SELECT create_hypertable('fund_flow_sector', 'date', chunk_time_interval => INTERVAL '1 year', if_not_exists => true);
SELECT create_hypertable('margin_stock', 'date', chunk_time_interval => INTERVAL '1 year', if_not_exists => true);
SELECT create_hypertable('sector_daily', 'date', chunk_time_interval => INTERVAL '1 year', if_not_exists => true);
SELECT create_hypertable('valuation_daily', 'date', chunk_time_interval => INTERVAL '1 year', if_not_exists => true);
SELECT create_hypertable('news_telegraph', 'pub_ts', chunk_time_interval => INTERVAL '1 month', if_not_exists => true);
SELECT create_hypertable('stock_news', 'pub_ts', chunk_time_interval => INTERVAL '1 month', if_not_exists => true);
SELECT create_hypertable('announcements', 'ann_date', chunk_time_interval => INTERVAL '1 month', if_not_exists => true);
SELECT create_hypertable('market_messages', 'msg_ts', chunk_time_interval => INTERVAL '1 month', if_not_exists => true);
SELECT create_hypertable('option_tquote', 'date', chunk_time_interval => INTERVAL '1 month', if_not_exists => true);
SELECT create_hypertable('option_greeks_iv', 'date', chunk_time_interval => INTERVAL '1 month', if_not_exists => true);
SELECT create_hypertable('radar_event', 'ts', chunk_time_interval => INTERVAL '7 days', if_not_exists => true);

-- Retention for minute-like tables
SELECT add_retention_policy('radar_event', INTERVAL '3 years', if_not_exists => true);

-- ==========================================
-- Record migration
-- ==========================================
INSERT INTO schema_migrations (version, checksum, note)
VALUES ('V002', md5('V002__m2_tables_sql'), 'M2 域表补齐: D4/D5/D6/D8/D9/D10/D11 + radar_event')
ON CONFLICT (version) DO NOTHING;
