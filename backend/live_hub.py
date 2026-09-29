"""
LiveHub — scalable WebSocket fan-out for Momentum Prop Engine.

- Local connection set per worker process
- Optional Redis Pub/Sub for cross-worker / multi-pod broadcast
- Works without Redis (single-process demo mode)
- Heartbeat + dead-socket pruning
- Channel-aware publish (default: mpe:live)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from fastapi import WebSocket
from starlette.websockets import WebSocketState

logger = logging.getLogger("mpe.live_hub")

DEFAULT_CHANNEL = "mpe:live"
HEARTBEAT_SECONDS = 30


class LiveHub:
    def __init__(
        self,
        redis_url: str | None = None,
        channel: str = DEFAULT_CHANNEL,
        heartbeat_seconds: float = HEARTBEAT_SECONDS,
    ) -> None:
        self.redis_url = redis_url or os.getenv("REDIS_URL") or os.getenv("MPE_REDIS_URL")
        self.channel = channel
        self.heartbeat_seconds = heartbeat_seconds
        self.local: set[WebSocket] = set()
        self._redis = None
        self._pubsub = None
        self._relay_task: asyncio.Task | None = None
        self._heartbeat_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._started = False

    @property
    def redis_enabled(self) -> bool:
        return bool(self.redis_url)

    @property
    def connection_count(self) -> int:
        return len(self.local)

    async def start(self) -> None:
        if self._started:
            return
        self._started = True

        if self.redis_url:
            try:
                import redis.asyncio as redis

                self._redis = redis.from_url(self.redis_url, decode_responses=True)
                self._pubsub = self._redis.pubsub()
                await self._pubsub.subscribe(self.channel)
                self._relay_task = asyncio.create_task(self._relay_loop(), name="mpe-redis-relay")
                logger.info("LiveHub Redis relay subscribed to %s", self.channel)
            except Exception as exc:
                logger.warning(
                    "LiveHub Redis unavailable (%s); falling back to local-only fan-out",
                    exc,
                )
                self._redis = None
                self._pubsub = None
        else:
            logger.info("LiveHub running local-only (set REDIS_URL for multi-worker scale)")

        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop(), name="mpe-ws-heartbeat")

    async def stop(self) -> None:
        self._started = False
        for task in (self._relay_task, self._heartbeat_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._relay_task = None
        self._heartbeat_task = None

        if self._pubsub is not None:
            try:
                await self._pubsub.unsubscribe(self.channel)
                await self._pubsub.aclose()
            except Exception:
                pass
            self._pubsub = None

        if self._redis is not None:
            try:
                await self._redis.aclose()
            except Exception:
                pass
            self._redis = None

        self.local.clear()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self.local.add(ws)
        logger.debug("WS connected; local=%s redis=%s", len(self.local), self.redis_enabled)

    def disconnect(self, ws: WebSocket) -> None:
        self.local.discard(ws)

    async def publish(self, payload: dict[str, Any], channel: str | None = None) -> None:
        text = json.dumps(payload, default=str)
        ch = channel or self.channel

        if self._redis is not None:
            try:
                await self._redis.publish(ch, text)
                return
            except Exception as exc:
                logger.warning("Redis publish failed (%s); local fan-out", exc)

        await self._send_local(text)

    async def _send_local(self, text: str) -> None:
        dead: list[WebSocket] = []
        async with self._lock:
            sockets = list(self.local)

        for ws in sockets:
            try:
                if ws.client_state != WebSocketState.CONNECTED:
                    dead.append(ws)
                    continue
                await ws.send_text(text)
            except Exception:
                dead.append(ws)

        if dead:
            async with self._lock:
                for ws in dead:
                    self.local.discard(ws)

    async def _relay_loop(self) -> None:
        assert self._pubsub is not None
        try:
            async for msg in self._pubsub.listen():
                if not self._started:
                    break
                if msg.get("type") != "message":
                    continue
                data = msg.get("data")
                if data is None:
                    continue
                if isinstance(data, bytes):
                    data = data.decode()
                await self._send_local(data)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Redis relay stopped: %s", exc)

    async def _heartbeat_loop(self) -> None:
        try:
            while self._started:
                await asyncio.sleep(self.heartbeat_seconds)
                if not self.local:
                    continue
                await self._send_local(
                    json.dumps({"type": "ping", "ts": asyncio.get_event_loop().time()})
                )
        except asyncio.CancelledError:
            raise
        except Exception as exp:
            logger.exception("Heartbeat loop error: %s", exp)
