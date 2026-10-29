"""Actual SQL permission gate, confined to the isolated qualification database.

This tool attempts prohibited operations inside transactions and always rolls
them back. A successful prohibited operation is a failure, never a passed test.
It emits counts/flags only, with no DSN, password or publisher text.
"""
import asyncio
import json
import os
import sys
from urllib.parse import urlsplit

import asyncpg

PROHIBITED = {
    'create_public_table': 'CREATE TABLE public.runtime_must_not_create(id integer)',
    'create_schema': 'CREATE SCHEMA runtime_must_not_create',
    'create_temporary_table': 'CREATE TEMP TABLE runtime_must_not_create(id integer)',
    'alter_application_table': 'ALTER TABLE public.cost_config ADD COLUMN runtime_must_not_create integer',
    'truncate_application_table': 'TRUNCATE public.cost_config',
    'alter_migration_revision': "UPDATE public.alembic_version SET version_num=version_num",
    'create_extension': 'CREATE EXTENSION hstore',
    'drop_application_table': 'DROP TABLE public.cost_config',
    'become_administrator': 'SET ROLE monitor_admin',
    'change_session_authorization': 'SET SESSION AUTHORIZATION monitor_admin',
    'grant_administrator': 'GRANT monitor_admin TO monitor',
    'elevate_role': 'ALTER ROLE monitor SUPERUSER',
    'read_authentication_catalog': 'SELECT rolpassword FROM pg_authid',
}


async def denied(connection, sql):
    transaction = connection.transaction()
    await transaction.start()
    try:
        await connection.execute(sql)
    except asyncpg.InsufficientPrivilegeError:
        return True
    finally:
        await transaction.rollback()
    return False


async def verify():
    url = os.environ.get('DATABASE_URL', '')
    parsed = urlsplit(url)
    if (parsed.scheme != 'postgresql+asyncpg' or parsed.username != 'monitor'
        or parsed.path != '/conflict_monitor_test'):
        raise ValueError('Use the restricted runtime login in an isolated conflict_monitor_test database')
    connection = await asyncpg.connect(url.replace('postgresql+asyncpg://', 'postgresql://', 1))
    try:
        flags = await connection.fetchrow('SELECT current_user AS name,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=current_user')
        memberships = await connection.fetchval('SELECT count(*) FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname=current_user)')
        owners = await connection.fetchval("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relowner=(SELECT oid FROM pg_roles WHERE rolname=current_user)")
        boundary_owners = await connection.fetchval("SELECT (SELECT count(*) FROM pg_database WHERE datname=current_database() AND datdba=(SELECT oid FROM pg_roles WHERE rolname=current_user)) + (SELECT count(*) FROM pg_namespace WHERE nspname='public' AND nspowner=(SELECT oid FROM pg_roles WHERE rolname=current_user))")
        checks = {'runtime_identity': flags['name']=='monitor',
            'no_administrative_flags': not any(flags[name] for name in ('rolsuper','rolcreatedb','rolcreaterole','rolreplication','rolbypassrls')),
            'no_role_memberships': memberships==0,'no_public_object_ownership': owners==0,
            'no_database_or_public_schema_ownership':boundary_owners==0,
            'migration_revision_readable': bool(await connection.fetchval('SELECT version_num FROM public.alembic_version'))}
        for name, sql in PROHIBITED.items():
            checks['denied_'+name] = await denied(connection, sql)
        # Required ordinary runtime capabilities: transaction advisory locks and sequence nextval.
        async with connection.transaction():
            checks['ordinary_advisory_lock_available'] = await connection.fetchval('SELECT pg_try_advisory_xact_lock($1)', 56182843097261030)
        # nextval is non-transactional: inspect its privilege instead of consuming a source ID.
        checks['sequence_usage_and_select_only'] = await connection.fetchval("SELECT has_sequence_privilege(current_user,'public.events_id_seq','USAGE') AND has_sequence_privilege(current_user,'public.events_id_seq','SELECT') AND NOT has_sequence_privilege(current_user,'public.events_id_seq','UPDATE')")
        report = {'scope':'actual_postgresql_runtime_permissions_isolated_database',
            'status':'PASS' if all(checks.values()) else 'FAIL/INCOMPLETE','checks':checks,
            'limitations':['DML persistence/read API/WebSocket behavior is qualified by the separate real PostGIS and pipeline gates.',
                'Only the dedicated test database is accepted; prohibited DDL is rolled back even if unexpectedly permitted.',
                'The migration administrator remains privileged by design and must not serve HTTP.']}
        print(json.dumps(report,indent=2))
        if not all(checks.values()):raise RuntimeError('Runtime permission boundary failed')
    finally:
        await connection.close()


if __name__=='__main__':
    try:
        asyncio.run(verify())
    except Exception as error:
        print(f'FAIL/INCOMPLETE: runtime permission qualification failed ({type(error).__name__})', file=sys.stderr)
        raise SystemExit(2) from None
