-- V002 里的主键写成了 LEFT(reason, 100)，PostgreSQL 不接受表达式主键，这张表从未建出来。
-- 这里用 (date, code, reason) 作为主键。上榜原因本身就短。

CREATE TABLE IF NOT EXISTS dragon_tiger (
  date          DATE NOT NULL,
  code          TEXT NOT NULL,
  name          TEXT,
  close         DOUBLE PRECISION,
  pct           DOUBLE PRECISION,
  reason        TEXT NOT NULL,
  turnover_rate DOUBLE PRECISION,
  amount        DOUBLE PRECISION,
  circ_mv       DOUBLE PRECISION,
  net_buy       DOUBLE PRECISION,
  buy_amount    DOUBLE PRECISION,
  sell_amount   DOUBLE PRECISION,
  buy_top5      JSONB,
  sell_top5     JSONB,
  inst_flag     BOOLEAN,
  inst_net      DOUBLE PRECISION,
  source        TEXT NOT NULL,
  ingest_ts     TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (date, code, reason)
);
COMMENT ON TABLE dragon_tiger IS 'D4 龙虎榜';

GRANT SELECT ON dragon_tiger TO duser_reader, duser_d12writer;
GRANT SELECT, INSERT, UPDATE, DELETE ON dragon_tiger TO duser_writer, duser_admin;

INSERT INTO schema_migrations (version) VALUES ('V009')
ON CONFLICT DO NOTHING;
