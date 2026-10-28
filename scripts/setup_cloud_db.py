"""Prepare a managed (cloud) PostgreSQL database, e.g. Neon, for the app. Idempotent.

    backend\\.venv\\Scripts\\python.exe scripts\\setup_cloud_db.py ^
        --owner-url "postgresql://OWNER:PASSWORD@HOST/DBNAME?sslmode=require" ^
        --reader-password "a-long-random-password"

Cloud plans give you a database and an owner role (no superuser), so this script uses
that owner as the admin role and creates:

* schemas ``raw``, ``analytics`` and ``app`` (owned by the owner role);
* the read-only role ``bi_reader``: LOGIN, SELECT on ``analytics`` only (also on future
  tables), no access to ``raw``/``app``, and role defaults
  ``default_transaction_read_only = on``, ``search_path = analytics``,
  ``statement_timeout = 30s``.

It prints the two SQLAlchemy URLs to paste into the backend host's environment.
"""

from __future__ import annotations

import argparse
import sys
from urllib.parse import quote, urlsplit, urlunsplit

import psycopg
from psycopg import sql


def libpq_url(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def with_credentials(url: str, user: str, password: str) -> str:
    """Return ``url`` with a different user/password, as a SQLAlchemy psycopg URL."""
    parts = urlsplit(libpq_url(url))
    host = parts.hostname or ""
    netloc = f"{quote(user)}:{quote(password, safe='')}@{host}"
    if parts.port:
        netloc += f":{parts.port}"
    out = urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
    return out.replace("postgresql://", "postgresql+psycopg://", 1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare a cloud PostgreSQL database.")
    parser.add_argument(
        "--owner-url", required=True, help="owner connection URL (direct, not pooled)"
    )
    parser.add_argument("--reader-password", required=True, help="password for the reader role")
    parser.add_argument("--reader-role", default="bi_reader", help="name of the read-only role")
    args = parser.parse_args()
    if len(args.reader_password) < 12:
        sys.exit("ERROR: use a reader password of at least 12 characters.")

    try:
        conn = psycopg.connect(libpq_url(args.owner_url), autocommit=True, connect_timeout=15)
    except psycopg.OperationalError as exc:
        sys.exit(f"ERROR: cannot connect with the owner URL: {exc}")

    with conn, conn.cursor() as cur:
        owner, db = cur.execute("SELECT current_user, current_database()").fetchone()
        print(f"Connected to database '{db}' as '{owner}'")

        for schema in ("raw", "analytics", "app"):
            cur.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))
            print(f"  schema {schema}: ready")

        reader = sql.Identifier(args.reader_role)
        exists = cur.execute(
            "SELECT 1 FROM pg_roles WHERE rolname = %s", (args.reader_role,)
        ).fetchone()
        verb = "ALTER" if exists else "CREATE"
        cur.execute(
            sql.SQL("{} ROLE {} WITH LOGIN PASSWORD {}").format(
                sql.SQL(verb), reader, sql.Literal(args.reader_password)
            )
        )
        print(f"  role {args.reader_role}: {'updated' if exists else 'created'}")

        ident = sql.Identifier(db)
        cur.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(ident, reader))
        cur.execute(sql.SQL("REVOKE ALL ON SCHEMA raw, app FROM {}").format(reader))
        cur.execute(sql.SQL("GRANT USAGE ON SCHEMA analytics TO {}").format(reader))
        cur.execute(sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA analytics TO {}").format(reader))
        cur.execute(
            sql.SQL(
                "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA analytics "
                "GRANT SELECT ON TABLES TO {}"
            ).format(sql.Identifier(owner), reader)
        )
        try:  # not every provider lets the owner change the public schema
            cur.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        except psycopg.Error as exc:
            print(f"  note: could not lock down schema public ({exc.sqlstate}); continuing")
        for setting in (
            "default_transaction_read_only = on",
            "search_path = analytics",
            "statement_timeout = '30s'",
        ):
            cur.execute(sql.SQL("ALTER ROLE {} SET " + setting).format(reader))
        print(f"  grants: {args.reader_role} -> SELECT on analytics only (read-only by default)")

    admin_url = libpq_url(args.owner_url).replace("postgresql://", "postgresql+psycopg://", 1)
    reader_url = with_credentials(args.owner_url, args.reader_role, args.reader_password)
    print("\nDone. Next:")
    print("  1. Load the data:")
    print(
        "     backend\\.venv\\Scripts\\python.exe database\\load_data.py "
        f'--database-url "{args.owner_url}" --drop-raw'
    )
    print("  2. Set these on the backend host (keep them secret):")
    print(f"     ADMIN_DATABASE_URL={admin_url}")
    print(f"     READER_DATABASE_URL={reader_url}")


if __name__ == "__main__":
    main()
