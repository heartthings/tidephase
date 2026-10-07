#!/bin/bash
set -e
# Init roles and permissions for market_tsdb
# Runs on first docker-compose up (docker-entrypoint-initdb.d)

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- ============================================
    -- Role creation (idempotent)
    -- ============================================

    -- duser_writer: 采集写入角色（仅采集表 DML）
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'duser_writer') THEN
            CREATE ROLE duser_writer WITH LOGIN PASSWORD '${DUSER_WRITER_PASSWORD}';
        END IF;
    END
    \$\$;
    ALTER ROLE duser_writer WITH PASSWORD '${DUSER_WRITER_PASSWORD}';

    -- duser_reader: 只读查询角色（API 用）
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'duser_reader') THEN
            CREATE ROLE duser_reader WITH LOGIN PASSWORD '${DUSER_READER_PASSWORD}';
        END IF;
    END
    \$\$;
    ALTER ROLE duser_reader WITH PASSWORD '${DUSER_READER_PASSWORD}';
    ALTER ROLE duser_reader SET statement_timeout = '30s';

    -- duser_admin: 运维角色（DDL/VACUUM/备份）
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'duser_admin') THEN
            CREATE ROLE duser_admin WITH LOGIN PASSWORD '${DUSER_ADMIN_PASSWORD}';
        END IF;
    END
    \$\$;
    ALTER ROLE duser_admin WITH PASSWORD '${DUSER_ADMIN_PASSWORD}';

    -- duser_d12writer: D12 认知/预测/基率 写入角色
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'duser_d12writer') THEN
            CREATE ROLE duser_d12writer WITH LOGIN PASSWORD '${DUSER_D12WRITER_PASSWORD}';
        END IF;
    END
    \$\$;
    ALTER ROLE duser_d12writer WITH PASSWORD '${DUSER_D12WRITER_PASSWORD}';

    -- ============================================
    -- Schema & default privileges
    -- ============================================
    -- Revoke default public schema access
    REVOKE ALL ON DATABASE market_tsdb FROM PUBLIC;
    GRANT CONNECT ON DATABASE market_tsdb TO duser_writer;
    GRANT CONNECT ON DATABASE market_tsdb TO duser_reader;
    GRANT CONNECT ON DATABASE market_tsdb TO duser_admin;
    GRANT CONNECT ON DATABASE market_tsdb TO duser_d12writer;

    GRANT USAGE ON SCHEMA public TO duser_writer;
    GRANT USAGE ON SCHEMA public TO duser_reader;
    GRANT ALL ON SCHEMA public TO duser_admin;
    GRANT USAGE ON SCHEMA public TO duser_d12writer;

    -- Writer: SELECT + INSERT + UPDATE on all tables (set after migration)
    GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO duser_writer;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE ON TABLES TO duser_writer;
    GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO duser_writer;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE ON SEQUENCES TO duser_writer;

    -- Reader: SELECT only
    GRANT SELECT ON ALL TABLES IN SCHEMA public TO duser_reader;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO duser_reader;

    -- D12 Writer: limited to cognition/prediction/base_rate (refined after migration)
    GRANT SELECT ON ALL TABLES IN SCHEMA public TO duser_d12writer;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO duser_d12writer;

    -- Admin: full control
    GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO duser_admin;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO duser_admin;
    GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO duser_admin;

EOSQL

echo "✅ Roles initialized: duser_writer, duser_reader, duser_admin, duser_d12writer"
