import asyncio

import pytest

from app.services.runtime import Runtime


@pytest.mark.asyncio
async def test_successful_retry_does_not_inherit_old_worker_failure():
    subject = Runtime()
    async def failed():
        raise ValueError("private provider URL/key")
    first = subject.start("manual_firms", failed())
    await asyncio.gather(first, return_exceptions=True)
    await asyncio.sleep(0)
    assert subject.snapshot()["workers"]["manual_firms"]["state"] == "failed"
    gate = asyncio.Event()
    retry = subject.start("manual_firms", gate.wait())
    try:
        snapshot = subject.snapshot()
        assert snapshot["workers"]["manual_firms"]["state"] == "running"
        assert snapshot["workers"]["manual_firms"]["error_type"] is None
        gate.set()
        await retry
        await asyncio.sleep(0)
        assert subject.snapshot()["workers"]["manual_firms"]["state"] == "stopped"
    finally:
        await subject.stop()


@pytest.mark.asyncio
async def test_cancellation_is_neither_worker_failure_nor_unobserved_exception():
    subject = Runtime()
    task = subject.start("pending", asyncio.Event().wait())
    await subject.stop()
    assert task.done() and task.cancelled()
    assert subject.failures == {}
    assert subject.snapshot()["workers"] == {}


@pytest.mark.asyncio
async def test_delayed_old_callback_cannot_fail_the_new_owner():
    subject = Runtime()
    old = asyncio.get_running_loop().create_future()
    old.set_exception(ValueError("private old-provider failure"))
    gate = asyncio.Event()
    replacement = subject.start("manual_firms", gate.wait())
    try:
        subject._finished("manual_firms", old)
        assert subject.tasks["manual_firms"] is replacement
        assert subject.failures == {}
        assert subject.snapshot()["workers"]["manual_firms"]["state"] == "running"
    finally:
        await subject.stop()


def test_failed_task_creation_does_not_clear_recorded_failure(monkeypatch):
    subject = Runtime()
    subject.failures["manual_firms"] = "ValueError"
    def failed_create(*args, **kwargs):
        raise RuntimeError("fixture scheduler unavailable")
    monkeypatch.setattr(asyncio, "create_task", failed_create)
    async def worker():
        pass
    coroutine = worker()
    try:
        with pytest.raises(RuntimeError, match="scheduler unavailable"):
            subject.start("manual_firms", coroutine)
        assert subject.failures == {"manual_firms": "ValueError"}
        assert subject.tasks == {}
    finally:
        coroutine.close()
