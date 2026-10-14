-- 六大指数按上海时区、以该段结束时间汇总成交量和成交额。
-- 10:00 = 09:30–10:00，11:00 = 10:00–11:00，11:30 = 11:00–11:30，
-- 14:00 = 13:00–14:00，15:00 = 14:00–15:00（含收盘这一分钟）。

CREATE OR REPLACE VIEW index_hour AS
SELECT bucket AS ts,
       code,
       sum(volume) AS volume,
       sum(amount) AS amount,
       count(*) AS bars
FROM (
  SELECT
    CASE
      WHEN (ts AT TIME ZONE 'Asia/Shanghai')::time = TIME '15:00:00'
      THEN time_bucket('1 hour', ts - INTERVAL '1 hour') + INTERVAL '1 hour'
      WHEN (ts AT TIME ZONE 'Asia/Shanghai')::time >= TIME '11:00:00'
       AND (ts AT TIME ZONE 'Asia/Shanghai')::time <= TIME '11:30:00'
      THEN time_bucket('1 hour', ts) + INTERVAL '30 minutes'
      ELSE time_bucket('1 hour', ts) + INTERVAL '1 hour'
    END AS bucket,
    code,
    volume,
    amount
  FROM index_minute
  WHERE freq = '1m'
) s
GROUP BY bucket, code;

COMMENT ON VIEW index_hour IS '六大指数按小时段结束时间汇总的成交量和成交额。点位是 10:00、11:00、11:30、14:00、15:00。成交额单位元，成交量与指数日线同一口径。';

GRANT SELECT ON index_hour TO duser_reader, duser_d12writer, duser_writer, duser_admin;

INSERT INTO schema_migrations (version, note)
VALUES ('V010', 'index_hour 视图：指数按小时汇总成交量和成交额')
ON CONFLICT (version) DO NOTHING;
