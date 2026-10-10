-- V005: lovetrade 全量迁移 — 新建 D6题材四表 + D12笔记两表 + D10 report + meta配置两表 + plate_movement_intraday
-- Z8 · 2026-10-10 · 铸码实装
-- 所有表含 source + ingest_ts 审计列，PK 幂等（ON CONFLICT upsert）

-- ─── D6 题材四表 ─────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS topic (
    topic_id        VARCHAR(32) NOT NULL PRIMARY KEY,
    theme_id        VARCHAR(32) NOT NULL UNIQUE,
    topic_group_id  VARCHAR(32),
    name            VARCHAR(255) NOT NULL,
    brief_intro     TEXT,
    introduction    TEXT,
    ai_introduction TEXT,
    source          VARCHAR(64) NOT NULL DEFAULT 'lovetrade-mysql',
    ingest_ts       TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE topic IS 'D6 题材表（lovetrade 迁移）';

CREATE TABLE IF NOT EXISTS topic_category (
    id          VARCHAR(32) NOT NULL PRIMARY KEY,
    topic_id    VARCHAR(32) NOT NULL REFERENCES topic(topic_id),
    parent_id   VARCHAR(32) NOT NULL DEFAULT '0',
    name        VARCHAR(255) NOT NULL,
    source      VARCHAR(64) NOT NULL DEFAULT 'lovetrade-mysql',
    ingest_ts   TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE topic_category IS 'D6 题材分类（树形，parent_id=0 为一级）';

CREATE TABLE IF NOT EXISTS topic_group (
    id          VARCHAR(32) NOT NULL PRIMARY KEY,
    name        VARCHAR(255) NOT NULL UNIQUE,
    source      VARCHAR(64) NOT NULL DEFAULT 'lovetrade-mysql',
    ingest_ts   TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE topic_group IS 'D6 题材分组';

CREATE TABLE IF NOT EXISTS topic_links (
    id              VARCHAR(32) NOT NULL PRIMARY KEY,
    source_topic_id VARCHAR(32) REFERENCES topic(topic_id),
    source_name     VARCHAR(255) NOT NULL,
    target_topic_id VARCHAR(32) REFERENCES topic(topic_id),
    target_name     VARCHAR(255) NOT NULL,
    relation        VARCHAR(255) NOT NULL,
    source          VARCHAR(64) NOT NULL DEFAULT 'lovetrade-mysql',
    ingest_ts       TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE topic_links IS 'D6 题材关联边（图谱）';

CREATE INDEX IF NOT EXISTS idx_topic_links_source ON topic_links(source_topic_id);
CREATE INDEX IF NOT EXISTS idx_topic_links_target ON topic_links(target_topic_id);
CREATE INDEX IF NOT EXISTS idx_topic_category_topic ON topic_category(topic_id);

-- ─── D12 笔记两表 ────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS note_category (
    id          VARCHAR(32) NOT NULL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    color       VARCHAR(16),
    status      SMALLINT NOT NULL DEFAULT 1,
    sort_order  INT NOT NULL DEFAULT 0,
    created_time TIMESTAMPTZ,
    updated_time TIMESTAMPTZ,
    source      VARCHAR(64) NOT NULL DEFAULT 'lovetrade-mysql',
    ingest_ts   TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE note_category IS 'D12 笔记分类';

CREATE TABLE IF NOT EXISTS trading_note (
    id          VARCHAR(32) NOT NULL PRIMARY KEY,
    category_id VARCHAR(32) NOT NULL REFERENCES note_category(id),
    title       VARCHAR(200) NOT NULL,
    content     TEXT NOT NULL,
    tags        VARCHAR(255),
    created_time TIMESTAMPTZ,
    updated_time TIMESTAMPTZ,
    source      VARCHAR(64) NOT NULL DEFAULT 'lovetrade-mysql',
    ingest_ts   TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE trading_note IS 'D12 交易笔记';

CREATE INDEX IF NOT EXISTS idx_trading_note_category ON trading_note(category_id);

-- ─── D10 report 表 ──────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS report (
    id              VARCHAR(32) NOT NULL PRIMARY KEY,
    type            VARCHAR(20) NOT NULL,
    title           VARCHAR(200) NOT NULL,
    content         TEXT NOT NULL,
    report_date     VARCHAR(20) NOT NULL,
    generate_time   TIMESTAMPTZ,
    send_status     SMALLINT DEFAULT 0,
    send_time       TIMESTAMPTZ,
    fail_reason     TEXT,
    create_time     TIMESTAMPTZ,
    update_time     TIMESTAMPTZ,
    source          VARCHAR(64) NOT NULL DEFAULT 'lovetrade-mysql',
    ingest_ts       TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE report IS 'D10 报告（早报/晚报/专题）';

CREATE INDEX IF NOT EXISTS idx_report_type ON report(type);
CREATE INDEX IF NOT EXISTS idx_report_date ON report(report_date);

-- ─── meta 配置两表 ──────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS dynamic_category_config (
    id          VARCHAR(32) NOT NULL PRIMARY KEY,
    status      SMALLINT NOT NULL,
    name        VARCHAR(64) NOT NULL,
    content     VARCHAR(256) NOT NULL,
    example     VARCHAR(256) NOT NULL,
    created_time TIMESTAMPTZ,
    source      VARCHAR(64) NOT NULL DEFAULT 'lovetrade-mysql',
    ingest_ts   TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE dynamic_category_config IS 'meta 动态分类配置';

CREATE TABLE IF NOT EXISTS trading_system_node (
    id          VARCHAR(32) NOT NULL PRIMARY KEY,
    parent_id   VARCHAR(32) NOT NULL DEFAULT '0',
    name        VARCHAR(32) NOT NULL,
    description TEXT,
    color       VARCHAR(16),
    sort_order  INT NOT NULL DEFAULT 0,
    created_time TIMESTAMPTZ,
    updated_time TIMESTAMPTZ,
    source      VARCHAR(64) NOT NULL DEFAULT 'lovetrade-mysql',
    ingest_ts   TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE trading_system_node IS 'meta 交易体系节点（树形）';

CREATE INDEX IF NOT EXISTS idx_trading_system_node_parent ON trading_system_node(parent_id);

-- ─── plate_movement_intraday（梁总批准降采样） ───────────────────────

CREATE TABLE IF NOT EXISTS plate_movement_intraday (
    ts          TIMESTAMPTZ NOT NULL,
    sector_code VARCHAR(16) NOT NULL,
    sector_name VARCHAR(64),
    kind        VARCHAR(16) NOT NULL DEFAULT 'concept',
    freq        VARCHAR(4) NOT NULL DEFAULT '5m',
    pct         DOUBLE PRECISION,
    close       DOUBLE PRECISION,
    main_net_inflow DOUBLE PRECISION,
    turnover    DOUBLE PRECISION,
    up_cnt      INT,
    down_cnt    INT,
    lead_stocks TEXT,
    source      VARCHAR(64) NOT NULL DEFAULT 'longhu',
    ingest_ts   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (ts, sector_code, freq)
);
COMMENT ON TABLE plate_movement_intraday IS '板块异动盘中5min降采样（梁总10-10批准）';

-- ─── 空表占位（源端 7 张空表） ──────────────────────────────────────
-- daily_market_performance: 0 rows
-- market_performance_data: 0 rows
-- speculative_performance_data: 0 rows
-- stock_market_data: 0 rows
-- home_summary: 1 row (→ 非空，迁移)
-- backfill_progress: 内部表，不迁移
-- announcements: 已有同名表在 target，跳过

-- ─── schema_migrations 记账 ─────────────────────────────────────────
INSERT INTO schema_migrations (version, applied_at, checksum, note)
VALUES ('V005', now(), 'z8_lovetrade_full_migration', 'lovetrade全量迁移: D6题材四表+D12笔记两表+D10 report+meta配置两表+plate_movement_intraday')
ON CONFLICT (version) DO NOTHING;
