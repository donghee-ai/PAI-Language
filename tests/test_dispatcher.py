"""language.ws.dispatcher.Dispatcher 단위 테스트.

핸들러 등록 / type별 라우팅 / 미등록·결손 케이스 처리.
"""

from __future__ import annotations

import pytest

from language.ws.dispatcher import Dispatcher
from shared.constants import TOPIC_ACTION_STATUS, TOPIC_VISION_UPDATE


# --- 라우팅 정상 동작 -------------------------------------------------------


@pytest.mark.asyncio
async def test_registered_handler_receives_matching_message() -> None:
    received: list[dict] = []

    async def handler(msg: dict) -> None:
        received.append(msg)

    d = Dispatcher()
    d.register(TOPIC_VISION_UPDATE, handler)

    msg = {"type": TOPIC_VISION_UPDATE, "data": {"objects": []}}
    await d.dispatch(msg)

    assert received == [msg]


@pytest.mark.asyncio
async def test_two_handlers_route_independently() -> None:
    vision_calls: list[dict] = []
    action_calls: list[dict] = []

    async def vision_handler(msg: dict) -> None:
        vision_calls.append(msg)

    async def action_handler(msg: dict) -> None:
        action_calls.append(msg)

    d = Dispatcher()
    d.register(TOPIC_VISION_UPDATE, vision_handler)
    d.register(TOPIC_ACTION_STATUS, action_handler)

    await d.dispatch({"type": TOPIC_VISION_UPDATE, "data": {}})
    await d.dispatch({"type": TOPIC_ACTION_STATUS, "data": {}})
    await d.dispatch({"type": TOPIC_VISION_UPDATE, "data": {"v": 2}})

    assert len(vision_calls) == 2
    assert len(action_calls) == 1


# --- 결손 / 미등록 케이스 ---------------------------------------------------


@pytest.mark.asyncio
async def test_message_without_type_field_is_ignored() -> None:
    called = False

    async def handler(_msg: dict) -> None:
        nonlocal called
        called = True

    d = Dispatcher()
    d.register(TOPIC_VISION_UPDATE, handler)

    await d.dispatch({"data": {"objects": []}})  # type 필드 없음
    assert called is False


@pytest.mark.asyncio
async def test_unregistered_type_is_ignored_silently() -> None:
    called = False

    async def handler(_msg: dict) -> None:
        nonlocal called
        called = True

    d = Dispatcher()
    d.register(TOPIC_VISION_UPDATE, handler)

    await d.dispatch({"type": "completely_unknown_type", "data": {}})
    assert called is False


@pytest.mark.asyncio
async def test_empty_message_is_ignored() -> None:
    d = Dispatcher()
    # 핸들러 등록 없이도 빈 메시지가 예외 없이 처리되어야 함
    await d.dispatch({})


# --- register 덮어쓰기 ------------------------------------------------------


@pytest.mark.asyncio
async def test_register_overwrites_previous_handler() -> None:
    first_calls: list[dict] = []
    second_calls: list[dict] = []

    async def first(msg: dict) -> None:
        first_calls.append(msg)

    async def second(msg: dict) -> None:
        second_calls.append(msg)

    d = Dispatcher()
    d.register(TOPIC_VISION_UPDATE, first)
    d.register(TOPIC_VISION_UPDATE, second)  # 덮어쓰기

    await d.dispatch({"type": TOPIC_VISION_UPDATE})

    assert first_calls == []
    assert len(second_calls) == 1
