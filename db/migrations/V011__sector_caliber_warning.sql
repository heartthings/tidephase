-- sector_daily.pct 在 2026-10-13 之前写的是龙虎 RealRankingInfo 第 4 列，不是当日涨跌幅。
-- 能从接口回补的日期会在重跑 j_sector_daily 时把 caliber_warning 清掉。

ALTER TABLE sector_daily
  ADD COLUMN IF NOT EXISTS caliber_warning TEXT;

COMMENT ON COLUMN sector_daily.caliber_warning IS '非空表示这一行的 pct 不能当作当日涨跌幅。空表示采集时写入的是当日涨跌幅。';

UPDATE sector_daily
SET caliber_warning = 'pct 来自龙虎第4列，不是当日涨跌幅。接口已不返回该日，无法回补。'
WHERE caliber_warning IS NULL
  AND date <= DATE '2026-10-13';

INSERT INTO schema_migrations (version, note)
VALUES ('V011', 'sector_daily.caliber_warning：标出不能当当日涨跌幅用的历史 pct')
ON CONFLICT (version) DO NOTHING;
