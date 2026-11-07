"""Actual public-reader SQL/API gate, only for conflict_monitor_test.

Prohibited operations are attempted in transactions and rolled back. No source
text, password or DSN is emitted. Standard catalog/function access is not a
universal SQL sandbox or a claim about every PostgreSQL side effect.
"""
import asyncio
import json
import os
import sys
from urllib.parse import urlsplit

import asyncpg
import httpx

PROHIBITED = {
    'private_reports_read': 'SELECT * FROM public.events LIMIT 1',
    'private_delivery_read': 'SELECT * FROM public.event_deliveries LIMIT 1',
    'private_delivery_state_read': 'SELECT * FROM public.event_delivery_state LIMIT 1',
    'publication_insert': "INSERT INTO public.public_observation_batches(id,source,published_at,status,payload) VALUES(repeat('a',64),'probe',now(),'failed','{}')",
    'publication_update': 'UPDATE public.public_observation_batches SET status=status WHERE FALSE',
    'publication_delete': 'DELETE FROM public.public_observation_batches WHERE FALSE',
    'aircraft_publication_insert': "INSERT INTO public.public_aircraft_batches(id,source,published_at,status,payload) VALUES(repeat('a',64),'probe',now(),'failed','{}')",
    'aircraft_publication_update': 'UPDATE public.public_aircraft_batches SET status=status WHERE FALSE',
    'aircraft_publication_delete': 'DELETE FROM public.public_aircraft_batches WHERE FALSE',
    'insert_report': "INSERT INTO public.events(source,raw_text) VALUES('qualification','synthetic privilege probe')",
    'update_report': 'UPDATE public.events SET raw_text=raw_text WHERE FALSE',
    'delete_report': 'DELETE FROM public.events WHERE FALSE',
    'truncate_report': 'TRUNCATE public.events',
    'insert_delivery': "INSERT INTO public.event_deliveries(event_id,stream,action) VALUES(1,'live','upsert')",
    'update_delivery': 'UPDATE public.event_deliveries SET publication_offset=publication_offset WHERE FALSE',
    'delete_delivery': 'DELETE FROM public.event_deliveries WHERE FALSE',
    'rewrite_watermark': 'UPDATE public.event_delivery_state SET last_offset=last_offset',
    'publisher_function': 'SELECT public.publish_event_deliveries()',
    'source_ledger': 'SELECT report FROM public.source_reports LIMIT 1',
    'operator_usage': 'SELECT * FROM public.usage_log LIMIT 1',
    'operator_costs': 'SELECT * FROM public.cost_config LIMIT 1',
    'operator_media': 'SELECT * FROM public.intel_media LIMIT 1',
    'migration_revision': 'SELECT version_num FROM public.alembic_version',
    'postgis_reference': 'SELECT srid FROM public.spatial_ref_sys LIMIT 1',
    'sequence_usage': "SELECT nextval('public.events_id_seq')",
    'sequence_value': 'SELECT last_value FROM public.events_id_seq',
    'large_object_create': 'SELECT pg_catalog.lo_create(0::oid)',
    'large_object_from_bytes': "SELECT pg_catalog.lo_from_bytea(0::oid,decode('','hex'))",
    'create_public_table': 'CREATE TABLE public.reader_must_not_create(id integer)',
    'create_schema': 'CREATE SCHEMA reader_must_not_create',
    'create_temporary_table': 'CREATE TEMP TABLE reader_must_not_create(id integer)',
    'alter_application_table': 'ALTER TABLE public.events ADD COLUMN reader_must_not_create integer',
    'drop_application_table': 'DROP TABLE public.cost_config',
    'become_writer': 'SET ROLE monitor',
    'become_administrator': 'SET ROLE monitor_admin',
    'change_session_authorization': 'SET SESSION AUTHORIZATION monitor_admin',
    'grant_writer': 'GRANT monitor TO monitor_public',
    'elevate_role': 'ALTER ROLE monitor_public SUPERUSER',
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
    from app.database_policy import PUBLIC_REPORT_TABLES, PUBLIC_ROLE
    from app.bootstrap import validate_public_privileges
    from app import main
    url = os.environ.get('DATABASE_URL', '')
    parsed = urlsplit(url)
    if (parsed.scheme != 'postgresql+asyncpg' or parsed.username != PUBLIC_ROLE
        or parsed.path != '/conflict_monitor_test' or parsed.query or parsed.fragment):
        raise ValueError('Use monitor_public in an isolated conflict_monitor_test database')
    if not main.settings.public_read_only:
        raise ValueError('Public API mode must be explicitly enabled for this qualification')
    connection = await asyncpg.connect(url.replace('postgresql+asyncpg://', 'postgresql://', 1))
    checks = {}
    try:
        role = await connection.fetchrow('SELECT current_user AS name,rolinherit,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=current_user')
        checks['reader_identity'] = role['name'] == PUBLIC_ROLE
        checks['no_inheritance_or_administrative_flags'] = not any(role[key] for key in ('rolinherit','rolsuper','rolcreatedb','rolcreaterole','rolreplication','rolbypassrls'))
        checks['no_role_memberships'] = 0 == await connection.fetchval('SELECT count(*) FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname=current_user) OR roleid=(SELECT oid FROM pg_roles WHERE rolname=current_user)')
        await validate_public_privileges(connection)
        checks['effective_privilege_audit_passed'] = True
        for table in sorted(PUBLIC_REPORT_TABLES):
            await connection.fetch(f'SELECT * FROM public."{table}" LIMIT 1')
            checks['read_' + table] = True
        for name, sql in PROHIBITED.items():
            checks['denied_' + name] = await denied(connection, sql)
        # Legacy whole-corpus switches must not reopen private tables or routes.
        main.settings.public_reports_enabled = True
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url='http://qualification') as client:
            for path in ('/health','/status','/config','/publication/observations','/publication/observations/download','/publication/aircraft'):
                checks['read_api_' + path] = (await client.get(path)).status_code == 200
            for path in ('/events','/events/time-range','/events/anomalies','/events/batch?ids=1','/events/delivery/baseline','/events/delivery/changes','/events/1','/events/1/location-candidates'):
                checks['denied_api_' + path] = (await client.get(path)).status_code == 503
        report = {'status': 'PASS' if all(checks.values()) else 'FAIL',
                  'scope': 'Actual public-reader application-database privileges and ASGI reads in isolated test database',
                  'checks': checks,
                  'limitations': ['Not a universal SQL execution sandbox or a test of every PostgreSQL side effect.',
                                  'No real publisher dataset or artifact is admitted by this fixture.']}
        print(json.dumps(report, indent=2))
        if not all(checks.values()):
            raise RuntimeError('Public reader privilege gate failed')
    finally:
        await connection.close()
        await main.engine.dispose()


if __name__ == '__main__':
    try:
        asyncio.run(verify())
    except Exception as error:
        print(f'FAIL/INCOMPLETE: public database qualification failed ({type(error).__name__})', file=sys.stderr)
        raise SystemExit(2) from None
