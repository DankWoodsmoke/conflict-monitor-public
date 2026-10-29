"""Task state is process evidence, not a claim that an upstream feed is healthy."""
import asyncio
from datetime import datetime, timezone


class Runtime:
    def __init__(self):
        self.tasks: dict[str, asyncio.Task] = {}
        self.failures: dict[str, str] = {}

    def start(self, name, coroutine):
        task = asyncio.create_task(coroutine, name=name)
        self.tasks[name] = task
        # A new task owns this name only after create_task succeeds. A failed
        # previous attempt remains visible until an actual retry is started.
        self.failures.pop(name, None)
        task.add_done_callback(lambda t: self._finished(name, t))
        return task

    def _finished(self, name, task):
        if self.tasks.get(name) is not task:
            # Consume replaced task exceptions without letting an old callback
            # label its newer replacement failed (or produce an unhandled task).
            if not task.cancelled():
                task.exception()
            return
        if not task.cancelled():
            error = task.exception()
            if error is not None:
                # Exception messages may contain provider keys/URLs: expose type only.
                self.failures[name] = type(error).__name__

    def snapshot(self):
        return {
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "workers": {name: {"state": "failed" if name in self.failures else
                "stopped" if task.done() else "running", "error_type": self.failures.get(name),
                "provider_health": "unverified"} for name, task in self.tasks.items()},
        }

    async def stop(self):
        for task in self.tasks.values():
            task.cancel()
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)
        self.tasks.clear()


runtime = Runtime()
