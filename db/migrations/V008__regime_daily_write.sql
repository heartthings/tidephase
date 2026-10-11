-- V008: regime_daily 补 note/indicators，并给 d12writer UPDATE（按 date upsert）
ALTER TABLE regime_daily ADD COLUMN IF NOT EXISTS note TEXT;
ALTER TABLE regime_daily ADD COLUMN IF NOT EXISTS indicators JSONB;

GRANT UPDATE ON TABLE regime_daily TO duser_d12writer;

INSERT INTO schema_migrations (version, checksum, note)
VALUES ('V008', md5('V008__regime_daily_write_sql'),
        'regime_daily.note + indicators；d12writer UPDATE，供 POST /d12/regime_daily')
ON CONFLICT (version) DO UPDATE SET note = EXCLUDED.note;
