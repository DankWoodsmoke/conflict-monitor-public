"""Public PostgreSQL grants are separate from the private writer and HTTP gates."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app import bootstrap, main
from app.database_policy import PUBLIC_REPORT_TABLES, PUBLIC_ROLE, POSTGIS_REFERENCE_TABLES


ADMIN_DSN = 'postgresql://monitor_admin:' + 'a' * 64 + '@db/conflict_monitor_test'


def public_role(**changes):
    return {'rolname': PUBLIC_ROLE, 'rolcanlogin': True, 'rolinherit': False,
            **dict.fromkeys(bootstrap.ROLE_FLAGS, False), **changes}


def administrator():
    return {'rolname': 'monitor_admin', 'rolcanlogin': True, **dict.fromkeys(bootstrap.ROLE_FLAGS, True)}


@pytest.mark.parametrize('value', ['', 'short', 'g' * 64, 'a' * 64, 'A' * 64, 'b' * 64, 'B' * 64])
def test_public_profile_requires_a_distinct_valid_reader_secret(value):
    with pytest.raises(ValueError):
        bootstrap.public_configuration({'PUBLIC_READ_ONLY': 'true', 'POSTGRES_PUBLIC_PASSWORD': value}, ADMIN_DSN, 'b' * 64)


def test_private_profile_remains_optional_but_validates_any_supplied_reader_secret():
    assert bootstrap.public_configuration({}, ADMIN_DSN, 'b' * 64) is None
    assert bootstrap.public_configuration({'POSTGRES_PUBLIC_PASSWORD': 'c' * 64}, ADMIN_DSN, 'b' * 64) == 'c' * 64
    with pytest.raises(ValueError):
        bootstrap.public_configuration({'POSTGRES_PUBLIC_PASSWORD': 'invalid'}, ADMIN_DSN, 'b' * 64)


@pytest.mark.parametrize('flag', [*bootstrap.ROLE_FLAGS, 'rolinherit'])
def test_existing_public_login_with_admin_or_inheritance_flags_is_rejected(flag):
    with pytest.raises(ValueError, match='prohibited privileges'):
        bootstrap.validate_roles([administrator(), public_role(**{flag: True})], [])


def test_public_role_is_recognized_but_membership_or_unknown_roles_remain_forbidden():
    bootstrap.validate_roles([administrator(), public_role()], [])
    with pytest.raises(ValueError, match='memberships'):
        bootstrap.validate_roles([administrator(), public_role()], [{'member': PUBLIC_ROLE}])
    with pytest.raises(ValueError, match='Unexpected'):
        bootstrap.validate_roles([administrator(), public_role(rolname='another_reader')], [])


@pytest.mark.asyncio
@pytest.mark.parametrize('index', range(11))
async def test_existing_public_privilege_findings_fail_before_silent_repair(index):
    connection = AsyncMock()
    connection.fetchval.side_effect = [0] * index + [1]
    with pytest.raises(ValueError, match='Existing public login has prohibited'):
        await bootstrap.validate_public_privileges(connection)
    assert connection.fetchval.await_count == index + 1
    connection.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_public_grants_are_select_only_and_preserve_only_preexisting_private_function_access(monkeypatch):
    connection = AsyncMock()
    connection.fetchval.side_effect = [list(PUBLIC_REPORT_TABLES), False, "'fixture-reader'", 'conflict_monitor_test', *([True] * (len(POSTGIS_REFERENCE_TABLES) + 1)), False, True]
    connection.fetch.return_value = [
        {'signature': 'pg_catalog.lo_create(oid)', 'private_can_execute': True},
        {'signature': 'pg_catalog.lo_import(text)', 'private_can_execute': False},
    ]
    preflight = AsyncMock()
    monkeypatch.setattr(bootstrap, 'preflight', preflight)
    assert await bootstrap.grant_public(connection, 'c' * 64) == len(PUBLIC_REPORT_TABLES)
    commands = [call.args[0] for call in connection.execute.await_args_list]
    reader_grants = [sql for sql in commands if sql.startswith('GRANT ') and sql.endswith('TO "monitor_public"')]
    assert set(reader_grants) == {
        'GRANT CONNECT ON DATABASE "conflict_monitor_test" TO "monitor_public"',
        'GRANT USAGE ON SCHEMA public TO "monitor_public"',
        *{f'GRANT SELECT ON TABLE public."{table}" TO "monitor_public"' for table in PUBLIC_REPORT_TABLES},
    }
    assert any('LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS' in sql for sql in commands)
    assert 'GRANT EXECUTE ON FUNCTION pg_catalog.lo_create(oid) TO "monitor"' in commands
    assert not any('GRANT EXECUTE ON FUNCTION pg_catalog.lo_import' in sql for sql in commands)
    assert 'REVOKE ALL ON FUNCTION public."publish_event_deliveries"() FROM PUBLIC, "monitor_public"' in commands
    assert sum(sql.startswith('REVOKE ALL PRIVILEGES ON TABLE ') and sql.endswith('FROM PUBLIC') for sql in commands) == len(POSTGIS_REFERENCE_TABLES)
    assert 'GRANT USAGE ON SCHEMA "topology" TO "monitor"' in commands
    assert 'GRANT USAGE ON SCHEMA "tiger" TO "monitor"' not in commands
    preflight.assert_awaited_once_with(connection)


@pytest.mark.asyncio
async def test_incomplete_public_schema_cannot_create_a_reader_login():
    connection = AsyncMock()
    connection.fetchval.return_value = ['events']
    with pytest.raises(ValueError, match='schema is incomplete'):
        await bootstrap.grant_public(connection, 'c' * 64)
    connection.execute.assert_not_awaited()


def test_migration_child_cannot_inherit_either_runtime_secret(monkeypatch):
    monkeypatch.setenv('POSTGRES_APP_PASSWORD', 'b' * 64)
    monkeypatch.setenv('POSTGRES_PUBLIC_PASSWORD', 'c' * 64)
    captured = {}
    def run(command, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(bootstrap.subprocess, 'run', run)
    bootstrap.run_migrations()
    assert 'POSTGRES_APP_PASSWORD' not in captured['env']
    assert 'POSTGRES_PUBLIC_PASSWORD' not in captured['env']


@pytest.mark.asyncio
async def test_public_health_only_reads_tables_granted_to_the_reader(monkeypatch):
    queries = []
    class ReaderSession:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def execute(self, query):
            sql = str(query)
            assert sql.split()[3] in PUBLIC_REPORT_TABLES
            queries.append(sql)
    monkeypatch.setattr(main.settings, 'public_read_only', True)
    monkeypatch.setattr(main, 'async_session', ReaderSession)
    monkeypatch.setattr(main, 'runtime', SimpleNamespace(failures={}))
    monkeypatch.setattr(main, 'delivery_status', lambda: {'status': 'idle'})
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url='http://fixture') as client:
        response = await client.get('/health')
    assert response.status_code == 200 and response.json() == {'status': 'healthy'}
    assert {sql.split()[3] for sql in queries} == PUBLIC_REPORT_TABLES
