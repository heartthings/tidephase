-- 认知、预测、反思、基率、交易体系和交易笔记搬到心库 mindbase（green/mindbase，mind-tsdb）。
-- tidephase 以后只存行情等基础数据。data_api、工具和 j_base_rate 都经 data_api/mind_db.py 或 secrets.yaml 的 mind 段连心库。
-- 搬家前的整表备份：green/mindbase/backup/tidephase_moved_tables_20261108.sql.gz

DROP VIEW IF EXISTS calibration_view;
DROP VIEW IF EXISTS reflection_journal;
DROP VIEW IF EXISTS cognition_current;
DROP TABLE IF EXISTS reflection;
DROP TABLE IF EXISTS prediction;
DROP TABLE IF EXISTS base_rate;
DROP TABLE IF EXISTS cognition;
DROP TABLE IF EXISTS trading_note;
DROP TABLE IF EXISTS note_category;
DROP TABLE IF EXISTS trading_system_node;

INSERT INTO schema_migrations (version, note)
VALUES ('V012', '认知、预测、反思、基率、交易体系和交易笔记搬到心库 mindbase')
ON CONFLICT (version) DO NOTHING;
