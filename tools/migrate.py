#!/usr/bin/env python3
"""
Migration runner for market-datalayer.
Idempotent: reads schema_migrations, skips already-applied versions.
Usage: python tools/migrate.py [--host HOST] [--port PORT] [--db DB] [--user USER] [--password PW]
"""
import argparse
import hashlib
import os
import sys
from pathlib import Path

import psycopg2
import yaml


MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "db" / "migrations"
SECRETS_PATH = Path(__file__).resolve().parent.parent / "configs" / "secrets.yaml"

# Ordered migration files
MIGRATION_FILES = [
    "V001__init_d0_d1_d2_d3_d7.sql",
    "V001__hypertables_policies.sql",
]


def load_secrets():
    if SECRETS_PATH.exists():
        with open(SECRETS_PATH) as f:
            return yaml.safe_load(f)
    return {}


def get_connection(args):
    secrets = load_secrets()
    return psycopg2.connect(
        host=args.host or os.getenv("MARKET_TSDB_HOST", "127.0.0.1"),
        port=args.port or int(os.getenv("MARKET_TSDB_PORT", "15432")),
        dbname=args.db or os.getenv("MARKET_TSDB_NAME", "market_tsdb"),
        user=args.user or os.getenv("MARKET_TSDB_USER", "postgres"),
        password=args.password or os.getenv("POSTGRES_PASSWORD", ""),
    )


def get_applied(conn):
    with conn.cursor() as cur:
        try:
            cur.execute("SELECT version FROM schema_migrations")
            return {row[0] for row in cur.fetchall()}
        except psycopg2.errors.UndefinedTable:
            return set()


def run_migration(conn, filepath, applied):
    version = filepath.stem
    if version in applied:
        print(f"  SKIP {version} (already applied)")
        return True

    sql = filepath.read_text(encoding="utf-8")
    checksum = hashlib.md5(sql.encode()).hexdigest()
    print(f"  APPLY {version} ...", end=" ")

    try:
        # Use autocommit for migration (some DDL can't be in transactions)
        old_autocommit = conn.autocommit
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.autocommit = old_autocommit
        print(f"OK (checksum={checksum[:8]})")
        return True
    except Exception as e:
        print(f"FAILED: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Run market-datalayer migrations")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--db", default=None)
    parser.add_argument("--user", default=None)
    parser.add_argument("--password", default=None)
    args = parser.parse_args()

    conn = get_connection(args)
    conn.autocommit = False

    applied = get_applied(conn)
    print(f"Already applied: {applied or '(none)'}")

    all_ok = True
    for fname in MIGRATION_FILES:
        fpath = MIGRATIONS_DIR / fname
        if not fpath.exists():
            print(f"  MISSING {fname}")
            all_ok = False
            continue
        if not run_migration(conn, fpath, applied):
            all_ok = False
            break

    # Verify
    applied_after = get_applied(conn)
    print(f"\nApplied after run: {applied_after}")
    conn.close()

    if all_ok:
        print("\n✅ Migration completed successfully.")
    else:
        print("\n❌ Migration had errors.")
        sys.exit(1)


if __name__ == "__main__":
    main()
