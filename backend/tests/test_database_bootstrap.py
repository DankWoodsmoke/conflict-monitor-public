"""Administrator credentials and DDL must remain outside the HTTP worker role."""
from unittest.mock import AsyncMock

import pytest

from app import bootstrap as subject


def roles(runtime=False):
    admin = {'rolname':'monitor_admin','rolcanlogin':True, **dict.fromkeys(subject.ROLE_FLAGS,True)}
    output = [admin]
    if runtime:
        output.append({'rolname':'monitor','rolcanlogin':True,**dict.fromkeys(subject.ROLE_FLAGS,False)})
    return output


def environment():
    return {'DATABASE_URL':'postgresql+asyncpg://monitor_admin:fixture-only-admin@127.0.0.1:5432/conflict_monitor_test',
        'POSTGRES_APP_PASSWORD':'a'*64}


@pytest.mark.parametrize('change', [
    {'DATABASE_URL':''},
    {'DATABASE_URL':'postgresql+asyncpg://monitor:fixture-only-admin@localhost/conflict_monitor'},
    {'DATABASE_URL':'postgresql+asyncpg://monitor_admin:fixture-only-admin@localhost/other_database'},
    {'DATABASE_URL':'postgresql+asyncpg://monitor_admin:fixture-only-admin@localhost/conflict_monitor?mode=runtime'},
    {'POSTGRES_APP_PASSWORD':'too-short'},
    {'POSTGRES_APP_PASSWORD':'g'*64},
    {'DATABASE_URL':environment()['DATABASE_URL'].replace('fixture-only-admin','a'*64)},
])
def test_invalid_or_shared_bootstrap_credentials_fail_before_connection(change):
    with pytest.raises(ValueError):
        subject.configuration({**environment(),**change})


def test_explicit_bootstrap_configuration_does_not_accept_runtime_dsn():
    dsn, fixture_runtime_secret = subject.configuration(environment())
    assert dsn.startswith('postgresql://monitor_admin:') and fixture_runtime_secret == 'a'*64


@pytest.mark.parametrize('flag', subject.ROLE_FLAGS)
def test_legacy_privileged_runtime_is_rejected_instead_of_silently_adopted(flag):
    value = roles(True); value[1][flag] = True
    with pytest.raises(ValueError,match='prohibited privileges'):
        subject.validate_roles(value,[])


def test_unknown_legacy_role_and_memberships_fail_closed():
    with pytest.raises(ValueError,match='Unexpected'):
        subject.validate_roles([*roles(True),{**roles()[0],'rolname':'legacy_admin'}],[])
    with pytest.raises(ValueError,match='memberships'):
        subject.validate_roles(roles(True),[{'role':'monitor_admin'}])
    subject.validate_roles(roles(True),[])


class Transaction:
    async def __aenter__(self):return self
    async def __aexit__(self,*args):return False


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['locked','preflight','migration','grants'])
async def test_initializer_failure_blocks_startup_and_always_closes_administrator_connection(monkeypatch,failure):
    connection = AsyncMock()
    connection.transaction = Transaction
    connection.fetchval.return_value = failure != 'locked'
    monkeypatch.setattr(subject.asyncpg,'connect',AsyncMock(return_value=connection))
    monkeypatch.setattr(subject,'configuration',lambda env:('postgresql://fixture', 'a'*64))
    preflight = AsyncMock(side_effect=ValueError('fixture failure') if failure=='preflight' else None,return_value=False)
    ensure = AsyncMock()
    grant = AsyncMock(side_effect=ValueError('fixture failure') if failure=='grants' else None,return_value=(8,5))
    migration_calls=[]
    def migrate():
        migration_calls.append(True)
        if failure=='migration':raise RuntimeError('fixture failure')
    monkeypatch.setattr(subject,'preflight',preflight)
    monkeypatch.setattr(subject,'ensure_runtime',ensure)
    monkeypatch.setattr(subject,'grant_runtime',grant)
    monkeypatch.setattr(subject,'run_migrations',migrate)
    with pytest.raises((ValueError,RuntimeError)):
        await subject.bootstrap()
    connection.close.assert_awaited_once()
    if failure in {'locked','preflight'}:
        ensure.assert_not_awaited(); assert not migration_calls
    if failure=='locked':connection.execute.assert_not_awaited()
    else:assert connection.execute.await_args.args[0]=='SELECT pg_advisory_unlock($1)'


def test_migration_child_receives_administrator_dsn_but_not_runtime_password(monkeypatch):
    monkeypatch.setenv('DATABASE_URL',environment()['DATABASE_URL'])
    monkeypatch.setenv('POSTGRES_APP_PASSWORD','a'*64)
    captured={}
    def run(command,**kwargs):
        captured.update(kwargs)
        return type('Result',(),{'returncode':0})()
    monkeypatch.setattr(subject.subprocess,'run',run)
    subject.run_migrations()
    assert captured['env']['DATABASE_URL']==environment()['DATABASE_URL']
    assert 'POSTGRES_APP_PASSWORD' not in captured['env']
    assert captured['capture_output'] is True


@pytest.mark.asyncio
async def test_ownership_preflight_blocks_role_reuse_before_migrations():
    connection=AsyncMock()
    connection.fetchval.side_effect=['monitor_admin',1,0,0]
    connection.fetch.side_effect=[roles(True),[]]
    with pytest.raises(ValueError,match='must not own'):
        await subject.preflight(connection)
