"""Create the bi_db database, its schemas and the two roles (idempotent).

Run as:  backend\\.venv\\Scripts\\python.exe scripts\\setup_db.py

Connects as the PostgreSQL superuser (password from .env) and:
  * creates roles ``bi_admin`` (owner) and ``bi_reader`` (read-only), or resets their passwords
  * creates database ``bi_db`` owned by ``bi_admin``
  * creates schemas ``raw``, ``analytics`` and ``app`` owned by ``bi_admin``
  * grants ``bi_reader`` SELECT on the ``analytics`` schema only (including future tables)

Safe to re-run at any time.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parent.parent


def load_env(path: Path) -> dict[str, str]:
    """Read KEY=VALUE pairs from a .env file (no external dependency needed)."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def setting(env: dict[str, str], key: str, default: str | None = None) -> str:
    """Return a setting from the process environment, then .env, then a default."""
    value = os.environ.get(key) or env.get(key) or default
    if value is None:
        sys.exit(f"ERROR: {key} is not set. Add it to {ROOT / '.env'} (see .env.example).")
    return value


def ensure_role(cur: psycopg.Cursor, name: str, password: str) -> None:
    """Create a login role, or reset its password if it already exists."""
    cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (name,))
    verb = "ALTER" if cur.fetchone() else "CREATE"
    cur.execute(
        sql.SQL("{} ROLE {} WITH LOGIN PASSWORD {}").format(
            sql.SQL(verb), sql.Identifier(name), sql.Literal(password)
        )
    )
    print(f"  role {name}: {'updated' if verb == 'ALTER' else 'created'}")


def main() -> None:
    env = load_env(ROOT / ".env")
    host = setting(env, "POSTGRES_HOST", "localhost")
    port = setting(env, "POSTGRES_PORT", "5432")
    superuser = setting(env, "POSTGRES_SUPERUSER", "postgres")
    su_password = setting(env, "POSTGRES_SUPERUSER_PASSWORD")
    db_name = setting(env, "POSTGRES_DB", "bi_db")
    admin_pw = setting(env, "BI_ADMIN_PASSWORD")
    reader_pw = setting(env, "BI_READER_PASSWORD")

    print(f"Connecting to PostgreSQL at {host}:{port} as {superuser} ...")
    try:
        server = psycopg.connect(
            host=host, port=port, user=superuser, password=su_password,
            dbname="postgres", autocommit=True, connect_timeout=10,
        )
    except psycopg.OperationalError as exc:
        sys.exit(f"ERROR: could not connect as {superuser}: {exc}")

    with server, server.cursor() as cur:
        ensure_role(cur, "bi_admin", admin_pw)
        ensure_role(cur, "bi_reader", reader_pw)
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
        if cur.fetchone():
            print(f"  database {db_name}: exists")
        else:
            cur.execute(
                sql.SQL("CREATE DATABASE {} OWNER bi_admin ENCODING 'UTF8' TEMPLATE template0").format(
                    sql.Identifier(db_name)
                )
            )
            print(f"  database {db_name}: created")

    db = psycopg.connect(
        host=host, port=port, user=superuser, password=su_password,
        dbname=db_name, autocommit=True,
    )
    with db, db.cursor() as cur:
        ident = sql.Identifier(db_name)
        cur.execute(sql.SQL("ALTER DATABASE {} OWNER TO bi_admin").format(ident))
        # Lock down the default public schema and database-level access.
        cur.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(ident))
        cur.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        cur.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO bi_admin, bi_reader").format(ident))

        for schema in ("raw", "analytics", "app"):
            cur.execute(
                sql.SQL("CREATE SCHEMA IF NOT EXISTS {} AUTHORIZATION bi_admin").format(
                    sql.Identifier(schema)
                )
            )
            cur.execute(sql.SQL("ALTER SCHEMA {} OWNER TO bi_admin").format(sql.Identifier(schema)))
            print(f"  schema {schema}: ready")

        # bi_reader: analytics only, SELECT only.
        cur.execute("REVOKE ALL ON SCHEMA raw, app FROM bi_reader")
        cur.execute("GRANT USAGE ON SCHEMA analytics TO bi_reader")
        cur.execute("GRANT SELECT ON ALL TABLES IN SCHEMA analytics TO bi_reader")
        cur.execute(
            "ALTER DEFAULT PRIVILEGES FOR ROLE bi_admin IN SCHEMA analytics "
            "GRANT SELECT ON TABLES TO bi_reader"
        )
        # Defensive defaults for the read-only role.
        cur.execute(sql.SQL("ALTER ROLE bi_reader IN DATABASE {} SET default_transaction_read_only = on").format(ident))
        cur.execute(sql.SQL("ALTER ROLE bi_reader IN DATABASE {} SET search_path = analytics").format(ident))
        cur.execute(sql.SQL("ALTER ROLE bi_reader IN DATABASE {} SET statement_timeout = '30s'").format(ident))
        cur.execute("ALTER ROLE bi_reader CONNECTION LIMIT 50")
        print("  grants: bi_reader -> SELECT on analytics (read-only)")

    print("Database setup complete.")


if __name__ == "__main__":
    main()
