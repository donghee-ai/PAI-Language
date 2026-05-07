"""Language 파트 진입점 — 이벤트 루프 조율.

실행: python -m language.main
"""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime, timezone

from shared.constants import (
    SENDER_LANGUAGE,
    TOPIC_ACTION_STATUS,
    TOPIC_ROBOT_COMMAND,
    TOPIC_VISION_UPDATE,
)
from language.config import Config
from language.context.vision_state import VisionState
from language.input.cli_handler import input_loop
from language.llm.openai_client import LLMClient
from language.llm.prompt_builder import SYSTEM_PROMPT, build_user_prompt
from language.llm.response_parser import parse_llm_response
from language.ws.client import HubClient
from language.ws.dispatcher import Dispatcher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)


class LanguageApp:
    """Language 파트 오케스트레이터."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.vision = VisionState()
        self.llm = LLMClient(config)
        self.hub = HubClient(config)
        self.dispatcher = Dispatcher()

        # 메시지 핸들러 등록
        self.dispatcher.register(TOPIC_VISION_UPDATE, self._on_vision_update)
        self.dispatcher.register(TOPIC_ACTION_STATUS, self._on_action_status)
        self.hub.on_message(self.dispatcher.dispatch)

    # -- 메시지 핸들러 --

    async def _on_vision_update(self, msg: dict) -> None:
        self.vision.update(msg.get("data", {}))
        log.info("Vision 업데이트: %s", self.vision.to_context_string())

    async def _on_action_status(self, msg: dict) -> None:
        data = msg.get("data", {})
        status = data.get("status", "unknown")
        action_ref = data.get("action_ref", "")
        message = data.get("message", "")
        print(f"\n[Action] {status} | {action_ref}: {message}")
        print("> ", end="", flush=True)

    # -- 사용자 입력 처리 --

    async def handle_user_input(self, user_text: str) -> None:
        """사용자 텍스트 → LLM → robot_command 전송."""
        vision_context = self.vision.to_context_string()
        user_prompt = build_user_prompt(user_text, vision_context)

        print("처리 중...")

        try:
            raw_response = await self.llm.chat(SYSTEM_PROMPT, user_prompt)
        except Exception as exc:
            print(f"[오류] LLM 호출 실패: {exc}")
            return

        # 대상 객체가 카메라에 보이는지 확인
        vision_confirmed = len(self.vision.get_objects()) > 0

        command = parse_llm_response(raw_response, user_text, vision_confirmed)

        # envelope 구성 후 전송
        envelope = {
            "type": TOPIC_ROBOT_COMMAND,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sender": SENDER_LANGUAGE,
            "data": command.model_dump(),
        }

        await self.hub.send(envelope)

        print(f"[명령 전송] action={command.action.value}, "
              f"target={command.target}, destination={command.destination}")
        print(f"[근거] {command.reasoning}")

    # -- 실행 --

    async def run(self) -> None:
        """WS 연결 + 사용자 입력 루프를 동시에 실행."""
        self.config.validate()

        print("=" * 50)
        print("PAI_LE Language 모듈")
        print(f"  WS: {self.config.ws_url}")
        print(f"  LLM: {self.config.openai_model}")
        print("  종료: quit / exit / Ctrl+C")
        print("=" * 50)

        ws_task = asyncio.create_task(self.hub.run())
        input_task = asyncio.create_task(input_loop(self.handle_user_input))

        # 입력 루프가 끝나면(사용자가 quit) 전체 종료
        done, pending = await asyncio.wait(
            [ws_task, input_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for t in pending:
            t.cancel()


def main() -> None:
    config = Config()
    app = LanguageApp(config)
    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        print("\n종료됨.")


if __name__ == "__main__":
    main()
