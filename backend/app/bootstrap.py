"""One-shot privileged database initialization; never imported by the HTTP app.

The runtime login owns no schema/table and receives only application DML,
application-sequence USAGE/SELECT, and migration-revision SELECT. Migrations run
with the separate administrator. Failures expose their type, never credentials.
"""
import asyncio
import os
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit

import asyncpg

ADMIN_ROLE = 'monitor_admin'
RUNTIME_ROLE = 'monitor'
LOCK_ID = 56182843097261029
ROLE_FLAGS = ('rolsuper', 'rolcreatedb', 'rolcreaterole', 'rolreplication', 'rolbypassrls')


def identifier(value):
    if not isinstance(value, str) or not value or '\x00' in value:
        raise ValueError('Invalid SQL identifier')
    return '"' + value.replace('"', '""') + '"'


def configuration(environ):
    url = environ.get('DATABASE_URL', '')
    parsed = urlsplit(url)
    password = environ.get('POSTGRES_APP_PASSWORD', '')
    if (parsed.scheme != 'postgresql+asyncpg' or parsed.username != ADMIN_ROLE
        or not parsed.password or not parsed.hostname
        or parsed.path not in {'/conflict_monitor', '/conflict_monitor_test'}
        or parsed.query or parsed.fragment):
        raise ValueError('Explicit bootstrap administrator DSN required')
    if not re.fullmatch('[0-9a-fA-F]{64}', password):
        raise ValueError('Runtime password must be a separately generated 64-character hex secret')
    if password == unquote(parsed.password):
        raise ValueError('Runtime and administrator passwords must be different')
    return url.replace('postgresql+asyncpg://', 'postgresql://', 1), password


def validate_roles(rows, memberships):
    roles = {row['rolname']: row for row in rows}
    if set(roles) - {ADMIN_ROLE, RUNTIME_ROLE}:
        raise ValueError('Unexpected non-system database role; explicit migration required')
    admin = roles.get(ADMIN_ROLE)
    if not admin or not admin['rolsuper'] or not admin['rolcanlogin']:
        raise ValueError('Expected bootstrap administrator is unavailable')
    runtime = roles.get(RUNTIME_ROLE)
    if runtime and (not runtime['rolcanlogin'] or any(runtime[flag] for flag in ROLE_FLAGS)):
        raise ValueError('Existing runtime login has prohibited privileges')
    if memberships:
        raise ValueError('Runtime role memberships require explicit review')


async def preflight(connection):
    if await connection.fetchval('SELECT current_user') != ADMIN_ROLE:
        raise ValueError('Bootstrap connection is not the dedicated administrator')
    rows = await connection.fetch("SELECT rolname,rolcanlogin,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname !~ '^pg_'")
    memberships = await connection.fetch("SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member WHERE r.rolname=$1", RUNTIME_ROLE)
    validate_roles(rows, memberships)
    owners = await connection.fetchval("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_roles r ON r.oid=c.relowner WHERE n.nspname='public' AND r.rolname=$1", RUNTIME_ROLE)
    schema_owner = await connection.fetchval("SELECT count(*) FROM pg_namespace n JOIN pg_roles r ON r.oid=n.nspowner WHERE n.nspname='public' AND r.rolname=$1", RUNTIME_ROLE)
    database_owner = await connection.fetchval("SELECT count(*) FROM pg_database d JOIN pg_roles r ON r.oid=d.datdba WHERE d.datname=current_database() AND r.rolname=$1", RUNTIME_ROLE)
    if owners or schema_owner or database_owner:
        raise ValueError('Runtime login must not own database, schema or application objects')
    return any(row['rolname'] == RUNTIME_ROLE for row in rows)


async def ensure_runtime(connection, password, exists):
    # quote_literal is parameterized; the resulting secret SQL is never logged.
    quoted = await connection.fetchval('SELECT quote_literal($1::text)', password)
    action = 'ALTER' if exists else 'CREATE'
    await connection.execute(f'{action} ROLE {identifier(RUNTIME_ROLE)} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {quoted}')


def run_migrations():
    child_environment = dict(os.environ)
    child_environment.pop('POSTGRES_APP_PASSWORD', None)
    result = subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'],
        env=child_environment, capture_output=True, timeout=120, check=False)
    if result.returncode:
        raise RuntimeError('Database migration failed; no HTTP service was started')


async def grant_runtime(connection, table_names):
    tables = sorted(table_names)
    existing = set(await connection.fetchval("SELECT array_agg(tablename) FROM pg_tables WHERE schemaname='public'") or [])
    if not set(tables).issubset(existing) or 'alembic_version' not in existing:
        raise ValueError('Application schema/revision is incomplete')
    runtime = identifier(RUNTIME_ROLE)
    database = identifier(await connection.fetchval('SELECT current_database()'))
    await connection.execute(f'REVOKE ALL PRIVILEGES ON DATABASE {database} FROM {runtime}')
    await connection.execute(f'REVOKE CREATE, TEMPORARY ON DATABASE {database} FROM PUBLIC')
    await connection.execute(f'GRANT CONNECT ON DATABASE {database} TO {runtime}')
    await connection.execute('REVOKE CREATE ON SCHEMA public FROM PUBLIC')
    await connection.execute(f'REVOKE ALL PRIVILEGES ON SCHEMA public FROM {runtime}')
    await connection.execute(f'GRANT USAGE ON SCHEMA public TO {runtime}')
    await connection.execute(f'REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM {runtime}')
    await connection.execute(f'REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM {runtime}')
    for name in tables:
        table = 'public.' + identifier(name)
        await connection.execute(f'REVOKE ALL PRIVILEGES ON TABLE {table} FROM PUBLIC')
        await connection.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {table} TO {runtime}')
    await connection.execute('REVOKE ALL PRIVILEGES ON TABLE public.alembic_version FROM PUBLIC')
    await connection.execute(f'GRANT SELECT ON TABLE public.alembic_version TO {runtime}')
    sequences = await connection.fetch("SELECT DISTINCT seq.relname FROM pg_class seq JOIN pg_namespace ns ON ns.oid=seq.relnamespace JOIN pg_depend d ON d.objid=seq.oid AND d.deptype IN ('a','i') JOIN pg_class t ON t.oid=d.refobjid JOIN pg_namespace tn ON tn.oid=t.relnamespace WHERE seq.relkind='S' AND ns.nspname='public' AND tn.nspname='public' AND t.relname=ANY($1::text[])", tables)
    for row in sequences:
        sequence = 'public.' + identifier(row['relname'])
        await connection.execute(f'REVOKE ALL PRIVILEGES ON SEQUENCE {sequence} FROM PUBLIC')
        await connection.execute(f'GRANT USAGE, SELECT ON SEQUENCE {sequence} TO {runtime}')
    # Do not automatically grant access to future/unreviewed tables.
    await connection.execute(f'ALTER DEFAULT PRIVILEGES FOR ROLE {identifier(ADMIN_ROLE)} IN SCHEMA public REVOKE ALL ON TABLES FROM {runtime}')
    await connection.execute(f'ALTER DEFAULT PRIVILEGES FOR ROLE {identifier(ADMIN_ROLE)} IN SCHEMA public REVOKE ALL ON SEQUENCES FROM {runtime}')
    await preflight(connection)
    return len(tables), len(sequences)


async def bootstrap():
    dsn, password = configuration(os.environ)
    connection = await asyncpg.connect(dsn)
    locked = False
    try:
        locked = await connection.fetchval('SELECT pg_try_advisory_lock($1)', LOCK_ID)
        if not locked:
            raise RuntimeError('Another database initializer holds the migration lock')
        async with connection.transaction():
            exists = await preflight(connection)
            await ensure_runtime(connection, password, exists)
        run_migrations()
        from app.models import Base
        tables = {table.name for table in Base.metadata.sorted_tables}
        async with connection.transaction():
            table_count, sequence_count = await grant_runtime(connection, tables)
        print(f'Database initialization complete: {table_count} application tables, {sequence_count} application sequences; runtime role restricted')
    finally:
        try:
            if locked:
                await connection.execute('SELECT pg_advisory_unlock($1)', LOCK_ID)
        finally:
            await connection.close()


if __name__ == '__main__':
    try:
        asyncio.run(bootstrap())
    except Exception as error:
        print(f'Database initialization failed ({type(error).__name__}); service startup blocked', file=sys.stderr)
        raise SystemExit(2) from None
