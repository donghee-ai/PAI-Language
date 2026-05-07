"""Action Hub WebSocket 클라이언트 — 연결, 재연결, 송수신 관리."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Callable, Coroutine

import websockets
from websockets.asyncio.client import ClientConnection

from language.config import Config

log = logging.getLogger(__name__)


class HubClient:
    """Action Hub에 대한 WebSocket 클라이언트."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._ws: ClientConnection | None = None
        self._on_message: Callable[[dict], Coroutine] | None = None
        self._connected = asyncio.Event()

    # -- public API --

    def on_message(self, handler: Callable[[dict], Coroutine]) -> None:
        """수신 메시지 콜백 등록."""
        self._on_message = handler

    async def send(self, payload: dict) -> None:
        """JSON 메시지 전송. 연결될 때까지 대기."""
        await self._connected.wait()
        if self._ws:
            await self._ws.send(json.dumps(payload, ensure_ascii=False))
            log.debug("sent: %s", payload.get("type"))

    async def run(self) -> None:
        """연결 루프 — 끊어지면 자동 재연결."""
        retries = 0
        while True:
            try:
                log.info("WS 연결 시도: %s", self._config.ws_url)
                async with websockets.connect(self._config.ws_url) as ws:
                    self._ws = ws
                    self._connected.set()
                    retries = 0
                    log.info("WS 연결 성공")
                    await self._recv_loop(ws)
            except (
                websockets.ConnectionClosed,
                websockets.InvalidURI,
                OSError,
            ) as exc:
                self._connected.clear()
                self._ws = None
                retries += 1
                max_r = self._config.ws_max_retries
                if max_r is not None and retries > max_r:
                    log.error("최대 재연결 횟수 초과 (%d)", max_r)
                    raise
                log.warning("WS 연결 끊김 (%s), %.1f초 후 재연결 (%d회차)",
                            exc, self._config.ws_reconnect_interval, retries)
                await asyncio.sleep(self._config.ws_reconnect_interval)

    # -- internal --

    async def _recv_loop(self, ws: ClientConnection) -> None:
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                log.warning("비정상 메시지 수신 (JSON 파싱 실패)")
                continue
            if self._on_message:
                await self._on_message(msg)
