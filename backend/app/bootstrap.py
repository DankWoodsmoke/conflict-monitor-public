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
from app.database_policy import PUBLIC_ROLE, PUBLIC_REPORT_TABLES, LEGACY_PUBLIC_REPORT_TABLES, POSTGIS_REFERENCE_TABLES, POSTGIS_REFERENCE_SEQUENCES, PUBLIC_BLOCKED_STORAGE_FUNCTIONS

ADMIN_ROLE = 'monitor_admin'
RUNTIME_ROLE = 'monitor'
LOCK_ID = 56182843097261029
ROLE_FLAGS = ('rolsuper', 'rolcreatedb', 'rolcreaterole', 'rolreplication', 'rolbypassrls')
DELIVERY_TABLES = {'event_delivery_state', 'event_deliveries'}


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


def public_configuration(environ, administrator_dsn, runtime_password):
    password = environ.get('POSTGRES_PUBLIC_PASSWORD', '')
    required = environ.get('PUBLIC_READ_ONLY', '').lower() in {'true', '1', 'yes', 'on'}
    if not password and not required:
        return None
    if not re.fullmatch('[0-9a-fA-F]{64}', password):
        raise ValueError('Public reader password must be a separately generated 64-character hex secret')
    administrator_password = unquote(urlsplit(administrator_dsn).password or '')
    if password.lower() in {runtime_password.lower(), administrator_password.lower()}:
        raise ValueError('Public, runtime and administrator passwords must be different')
    return password


def validate_roles(rows, memberships):
    roles = {row['rolname']: row for row in rows}
    if set(roles) - {ADMIN_ROLE, RUNTIME_ROLE, PUBLIC_ROLE}:
        raise ValueError('Unexpected non-system database role; explicit migration required')
    admin = roles.get(ADMIN_ROLE)
    if not admin or not admin['rolsuper'] or not admin['rolcanlogin']:
        raise ValueError('Expected bootstrap administrator is unavailable')
    runtime = roles.get(RUNTIME_ROLE)
    if runtime and (not runtime['rolcanlogin'] or any(runtime[flag] for flag in ROLE_FLAGS)):
        raise ValueError('Existing runtime login has prohibited privileges')
    public = roles.get(PUBLIC_ROLE)
    if public and (not public['rolcanlogin'] or public.get('rolinherit', True)
                   or any(public[flag] for flag in ROLE_FLAGS)):
        raise ValueError('Existing public login has prohibited privileges')
    if memberships:
        raise ValueError('Runtime role memberships require explicit review')


async def preflight(connection, allow_legacy_public=False):
    if await connection.fetchval('SELECT current_user') != ADMIN_ROLE:
        raise ValueError('Bootstrap connection is not the dedicated administrator')
    rows = await connection.fetch("SELECT rolname,rolcanlogin,rolinherit,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname !~ '^pg_'")
    memberships = await connection.fetch("SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member OR r.oid=m.roleid WHERE r.rolname=ANY($1::text[])", [RUNTIME_ROLE, PUBLIC_ROLE])
    validate_roles(rows, memberships)
    owners = await connection.fetchval("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_roles r ON r.oid=c.relowner WHERE n.nspname='public' AND r.rolname=$1", RUNTIME_ROLE)
    schema_owner = await connection.fetchval("SELECT count(*) FROM pg_namespace n JOIN pg_roles r ON r.oid=n.nspowner WHERE n.nspname='public' AND r.rolname=$1", RUNTIME_ROLE)
    database_owner = await connection.fetchval("SELECT count(*) FROM pg_database d JOIN pg_roles r ON r.oid=d.datdba WHERE d.datname=current_database() AND r.rolname=$1", RUNTIME_ROLE)
    if owners or schema_owner or database_owner:
        raise ValueError('Runtime login must not own database, schema or application objects')
    if any(row['rolname'] == PUBLIC_ROLE for row in rows):
        await validate_public_privileges(connection, allow_legacy_public=allow_legacy_public)
    return any(row['rolname'] == RUNTIME_ROLE for row in rows)


async def ensure_runtime(connection, password, exists):
    # quote_literal is parameterized; the resulting secret SQL is never logged.
    quoted = await connection.fetchval('SELECT quote_literal($1::text)', password)
    action = 'ALTER' if exists else 'CREATE'
    await connection.execute(f'{action} ROLE {identifier(RUNTIME_ROLE)} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {quoted}')


def run_migrations():
    child_environment = dict(os.environ)
    child_environment.pop('POSTGRES_APP_PASSWORD', None)
    child_environment.pop('POSTGRES_PUBLIC_PASSWORD', None)
    result = subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'],
        env=child_environment, capture_output=True, timeout=120, check=False)
    if result.returncode:
        raise RuntimeError('Database migration failed; no HTTP service was started')


async def grant_runtime(connection, table_names):
    tables = sorted(table_names)
    existing = set(await connection.fetchval("SELECT array_agg(tablename) FROM pg_tables WHERE schemaname='public'") or [])
    if not set(tables).issubset(existing) or 'alembic_version' not in existing:
        raise ValueError('Application schema/revision is incomplete')
    if not DELIVERY_TABLES.issubset(existing) or DELIVERY_TABLES.intersection(tables):
        raise ValueError('Delivery schema must be present outside the application DML grants')
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
        rights = 'SELECT, INSERT, DELETE' if name in PUBLIC_REPORT_TABLES else 'SELECT, INSERT, UPDATE, DELETE'
        await connection.execute(f'GRANT {rights} ON TABLE {table} TO {runtime}')
    await connection.execute('REVOKE ALL PRIVILEGES ON TABLE public.alembic_version FROM PUBLIC')
    await connection.execute(f'GRANT SELECT ON TABLE public.alembic_version TO {runtime}')
    for name in sorted(DELIVERY_TABLES):
        table = 'public.' + identifier(name)
        await connection.execute(f'REVOKE ALL PRIVILEGES ON TABLE {table} FROM PUBLIC')
        await connection.execute(f'GRANT SELECT ON TABLE {table} TO {runtime}')
    await connection.execute('REVOKE ALL ON FUNCTION public.publish_event_deliveries() FROM PUBLIC')
    await connection.execute(f'GRANT EXECUTE ON FUNCTION public.publish_event_deliveries() TO {runtime}')
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


async def validate_public_privileges(connection, allow_legacy_public=False):
    """Reject an existing overprivileged reader; do not silently adopt it.

    Effective privilege functions include inherited PUBLIC and column ACLs.
    Built-in catalog reads and ordinary PostGIS function execution remain; this
    is an application-data boundary, not a universal SQL execution sandbox.
    """
    checks = [
        ("ownership", """SELECT count(*) FROM pg_shdepend d JOIN pg_roles r ON r.oid=d.refobjid
            WHERE d.refclassid='pg_authid'::regclass AND r.rolname=$1 AND d.deptype='o'""", []),
        ("database creation or temporary objects", """SELECT has_database_privilege($1,current_database(),'CREATE,TEMPORARY')::int""", []),
        ("schema creation or delegated access", """SELECT count(*) FROM pg_namespace n
            WHERE has_schema_privilege($1,n.oid,'CREATE,USAGE WITH GRANT OPTION')""", []),
        ("table or column access", """SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE CASE WHEN n.nspname !~ '^pg_' AND n.nspname<>'information_schema' AND c.relkind IN ('r','p','v','m','f')
            THEN (has_table_privilege($1,c.oid,'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER,MAINTAIN,SELECT WITH GRANT OPTION')
              OR has_any_column_privilege($1,c.oid,'INSERT,UPDATE,REFERENCES,SELECT WITH GRANT OPTION')
              OR ((n.nspname<>'public' OR NOT c.relname=ANY($2::text[]))
                  AND has_any_column_privilege($1,c.oid,'SELECT'))) ELSE FALSE END""", [sorted(PUBLIC_REPORT_TABLES | (LEGACY_PUBLIC_REPORT_TABLES if allow_legacy_public else frozenset()))]),
        ("sequence access", """SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE CASE WHEN c.relkind='S' AND n.nspname !~ '^pg_'
                THEN has_sequence_privilege($1,c.oid,'USAGE,SELECT,UPDATE') ELSE FALSE END""", []),
        ("definer or publisher function execution", """SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
            WHERE n.nspname !~ '^pg_' AND n.nspname<>'information_schema'
            AND (p.prosecdef OR p.proname IN ('publish_event_deliveries','enqueue_event_delivery'))
            AND has_function_privilege($1,p.oid,'EXECUTE')""", []),
        ("explicit function access", """SELECT count(*) FROM pg_proc p, LATERAL aclexplode(p.proacl) a
            WHERE a.grantee=(SELECT oid FROM pg_roles WHERE rolname=$1)""", []),
        ("large-object mutation functions", """SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
            WHERE n.nspname='pg_catalog' AND p.proname=ANY($2::text[]) AND has_function_privilege($1,p.oid,'EXECUTE')""", [sorted(PUBLIC_BLOCKED_STORAGE_FUNCTIONS)]),
        # PG17 has no has_largeobject_privilege helper. With role memberships
        # prohibited, direct/PUBLIC ACL entries and ownership cover its access.
        ("large-object access", """SELECT count(*) FROM pg_largeobject_metadata l,
            LATERAL aclexplode(COALESCE(l.lomacl,acldefault('L',l.lomowner))) a
            WHERE a.grantee=0 OR a.grantee=(SELECT oid FROM pg_roles WHERE rolname=$1)""", []),
        ("automatic future grants", """SELECT count(*) FROM pg_default_acl d, LATERAL aclexplode(d.defaclacl) a
            WHERE a.grantee=(SELECT oid FROM pg_roles WHERE rolname=$1)
               OR (a.grantee=0 AND d.defaclobjtype IN ('r','S'))""", []),
        ("unexpected login defaults", """SELECT count(*) FROM pg_db_role_setting
            WHERE setrole=(SELECT oid FROM pg_roles WHERE rolname=$1)""", []),
    ]
    for label, query, extra in checks:
        if await connection.fetchval(query, PUBLIC_ROLE, *extra):
            raise ValueError(f'Existing public login has prohibited {label}; explicit review required')
    if allow_legacy_public:
        # A known old SELECT grant may be removed, but column/delegated/PUBLIC
        # grants were never part of that profile and must not be silently adopted.
        unexpected = await connection.fetchval("""SELECT count(*) FROM pg_class c
            JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_attribute a ON a.attrelid=c.oid,
            LATERAL aclexplode(a.attacl) acl WHERE n.nspname='public' AND c.relname=ANY($2::text[])
            AND (acl.grantee=0 OR acl.grantee=(SELECT oid FROM pg_roles WHERE rolname=$1))""",
            PUBLIC_ROLE, sorted(LEGACY_PUBLIC_REPORT_TABLES))
        if unexpected:
            raise ValueError('Legacy public column grants require explicit review')


async def retire_legacy_public_grants(connection):
    """Narrow an audited prior reader before migration, even on private reruns."""
    if not await connection.fetchval('SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=$1)', PUBLIC_ROLE):
        return
    for table in sorted(LEGACY_PUBLIC_REPORT_TABLES):
        if await connection.fetchval('SELECT to_regclass($1)', 'public.' + table):
            await connection.execute(f'REVOKE ALL ON TABLE public.{identifier(table)} FROM {identifier(PUBLIC_ROLE)}')
    await validate_public_privileges(connection)


async def grant_public(connection, password):
    existing = set(await connection.fetchval("SELECT array_agg(tablename) FROM pg_tables WHERE schemaname='public'") or [])
    if not PUBLIC_REPORT_TABLES.issubset(existing):
        raise ValueError('Public report schema is incomplete')
    exists = await connection.fetchval('SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=$1)', PUBLIC_ROLE)
    quoted = await connection.fetchval('SELECT quote_literal($1::text)', password)
    reader = identifier(PUBLIC_ROLE)
    action = 'ALTER' if exists else 'CREATE'
    await connection.execute(f'{action} ROLE {reader} LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {quoted}')
    database = identifier(await connection.fetchval('SELECT current_database()'))
    await connection.execute(f'REVOKE ALL PRIVILEGES ON DATABASE {database} FROM {reader}')
    await connection.execute(f'GRANT CONNECT ON DATABASE {database} TO {reader}')
    await connection.execute(f'REVOKE ALL PRIVILEGES ON SCHEMA public FROM {reader}')
    await connection.execute(f'GRANT USAGE ON SCHEMA public TO {reader}')
    await connection.execute(f'REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM {reader}')
    await connection.execute(f'REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM {reader}')
    await connection.execute(f'REVOKE ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public FROM {reader}')
    for name in sorted(PUBLIC_REPORT_TABLES):
        await connection.execute(f'GRANT SELECT ON TABLE public.{identifier(name)} TO {reader}')
    # PUBLIC is additive: revoking just the role cannot remove these PostGIS
    # reference-table defaults. Retain the private monitor's existing read access.
    for schema, name in sorted(POSTGIS_REFERENCE_TABLES):
        table = f'{identifier(schema)}.{identifier(name)}'
        private_select = await connection.fetchval("SELECT has_table_privilege($1,$2,'SELECT')", RUNTIME_ROLE, table)
        await connection.execute(f'REVOKE ALL PRIVILEGES ON TABLE {table} FROM PUBLIC')
        if private_select:
            await connection.execute(f'GRANT SELECT ON TABLE {table} TO {identifier(RUNTIME_ROLE)}')
    for schema, name in sorted(POSTGIS_REFERENCE_SEQUENCES):
        sequence = f'{identifier(schema)}.{identifier(name)}'
        private_select = await connection.fetchval("SELECT has_sequence_privilege($1,$2,'SELECT')", RUNTIME_ROLE, sequence)
        await connection.execute(f'REVOKE ALL PRIVILEGES ON SEQUENCE {sequence} FROM PUBLIC')
        if private_select:
            await connection.execute(f'GRANT SELECT ON SEQUENCE {sequence} TO {identifier(RUNTIME_ROLE)}')
    for schema in ('tiger', 'topology'):
        private_usage = await connection.fetchval('SELECT has_schema_privilege($1,$2,\'USAGE\')', RUNTIME_ROLE, schema)
        await connection.execute(f'REVOKE USAGE ON SCHEMA {identifier(schema)} FROM PUBLIC')
        if private_usage:
            await connection.execute(f'GRANT USAGE ON SCHEMA {identifier(schema)} TO {identifier(RUNTIME_ROLE)}')
    for name in ('publish_event_deliveries', 'enqueue_event_delivery'):
        await connection.execute(f'REVOKE ALL ON FUNCTION public.{identifier(name)}() FROM PUBLIC, {reader}')
    storage_functions = await connection.fetch("""SELECT format('%I.%I(%s)',n.nspname,p.proname,pg_get_function_identity_arguments(p.oid)) AS signature,
        has_function_privilege($1,p.oid,'EXECUTE') AS private_can_execute
        FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        WHERE n.nspname='pg_catalog' AND p.proname=ANY($2::text[])""", RUNTIME_ROLE, sorted(PUBLIC_BLOCKED_STORAGE_FUNCTIONS))
    for function in storage_functions:
        await connection.execute(f'REVOKE ALL ON FUNCTION {function["signature"]} FROM PUBLIC, {reader}')
        if function['private_can_execute']:
            await connection.execute(f'GRANT EXECUTE ON FUNCTION {function["signature"]} TO {identifier(RUNTIME_ROLE)}')
    for kind in ('TABLES', 'SEQUENCES', 'FUNCTIONS'):
        await connection.execute(f'ALTER DEFAULT PRIVILEGES FOR ROLE {identifier(ADMIN_ROLE)} IN SCHEMA public REVOKE ALL ON {kind} FROM {reader}')
    await preflight(connection)
    return len(PUBLIC_REPORT_TABLES)


async def bootstrap():
    dsn, password = configuration(os.environ)
    public_password = public_configuration(os.environ, dsn, password)
    connection = await asyncpg.connect(dsn)
    locked = False
    try:
        locked = await connection.fetchval('SELECT pg_try_advisory_lock($1)', LOCK_ID)
        if not locked:
            raise RuntimeError('Another database initializer holds the migration lock')
        async with connection.transaction():
            exists = await preflight(connection, allow_legacy_public=True)
            await retire_legacy_public_grants(connection)
            await ensure_runtime(connection, password, exists)
        run_migrations()
        from app.models import Base
        tables = {table.name for table in Base.metadata.sorted_tables}
        async with connection.transaction():
            table_count, sequence_count = await grant_runtime(connection, tables)
            if public_password is not None:
                await grant_public(connection, public_password)
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
