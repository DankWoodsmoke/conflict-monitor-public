"""Bounded per-client queues keep slow browsers out of the ingestion path."""
import asyncio
from fastapi import WebSocket


class Broadcaster:
    def __init__(self, max_clients=128, queue_size=32):
        self._clients = {}
        self._senders = {}
        self._pending = {}
        self._lock = asyncio.Lock()
        self._stopping = False
        self.max_clients = max_clients
        self.queue_size = queue_size

    async def connect(self, ws: WebSocket):
        async with self._lock:
            if ws in self._clients:
                return True
            pending = self._pending.get(ws)
            rejected = self._stopping or (pending is None and
                len(self._clients) + len(self._pending) >= self.max_clients)
            if not rejected and pending is None:
                pending = asyncio.create_task(self._accept(ws), name="websocket_handshake")
                self._pending[ws] = pending
        # Socket I/O must never run under the shared registry lock.
        if rejected:
            await self._close(ws, code=1013)
            return False
        try:
            return await asyncio.shield(pending)
        except asyncio.CancelledError:
            await self.disconnect(ws)
            raise

    async def _accept(self, ws):
        accepted = False
        try:
            await asyncio.wait_for(ws.accept(), timeout=2)
            async with self._lock:
                if not self._stopping:
                    queue = asyncio.Queue(maxsize=self.queue_size)
                    self._clients[ws] = queue
                    self._senders[ws] = asyncio.create_task(self._send(ws, queue), name="websocket_sender")
                    accepted = True
            return accepted
        except Exception:
            return False
        finally:
            async with self._lock:
                if self._pending.get(ws) is asyncio.current_task():
                    self._pending.pop(ws, None)
            if not accepted:
                await self._close(ws)

    async def _close(self, ws, code=1000):
        try:
            await asyncio.wait_for(ws.close(code=code), timeout=.25)
        except Exception:
            pass

    async def _send(self, ws, queue):
        try:
            while True:
                await asyncio.wait_for(ws.send_text(await queue.get()), timeout=2)
        except (Exception, asyncio.CancelledError):
            pass
        finally:
            await self.disconnect(ws)

    async def disconnect(self, ws):
        async with self._lock:
            self._clients.pop(ws, None)
            sender = self._senders.pop(ws, None)
            pending = self._pending.pop(ws, None)
        tasks = [task for task in (sender, pending) if task and task is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await self._close(ws)

    async def broadcast(self, message):
        async with self._lock:
            clients = list(self._clients.items())
        for ws, queue in clients:
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                task = self._senders.get(ws)
                if task:
                    task.cancel()

    async def stop(self):
        async with self._lock:
            self._stopping = True
            sockets = set(self._clients) | set(self._pending)
        await asyncio.gather(*(self.disconnect(ws) for ws in sockets), return_exceptions=True)

    def start(self):
        """Reset admission when a new application lifespan begins."""
        self._stopping = False


broadcaster = Broadcaster()
