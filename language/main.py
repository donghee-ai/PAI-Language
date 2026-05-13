"""Language 파트 진입점 — 이벤트 루프 조율.

실행: python -m language.main
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

import openai

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

# vision_update 로그 throttle 주기 — 카메라가 보통 10Hz로 송출하므로 매 프레임 INFO를
# 찍으면 사용자 입력 prompt가 묻힌다. 매 프레임은 DEBUG로, INFO 요약은 이 간격으로만.
VISION_LOG_THROTTLE_SEC = 1.0

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)


class LanguageApp:
    """Language 파트 오케스트레이터."""

    def __init__(self, config: Config, *, emit=None) -> None:
        self.config = config
        # 사용자 대상 출력 싱크. 기본은 stdout(CLI). GUI 등은 콜백을 주입해 가로챈다.
        self.emit = emit if emit is not None else print
        self.vision = VisionState()
        self.llm = LLMClient(config)
        self.hub = HubClient(config)
        self.dispatcher = Dispatcher()
        self._last_vision_info_log = 0.0

        # 메시지 핸들러 등록
        self.dispatcher.register(TOPIC_VISION_UPDATE, self._on_vision_update)
        self.dispatcher.register(TOPIC_ACTION_STATUS, self._on_action_status)
        self.hub.on_message(self.dispatcher.dispatch)

    # -- 메시지 핸들러 --

    async def _on_vision_update(self, msg: dict) -> None:
        self.vision.update(msg.get("data", {}))
        # 매 프레임은 DEBUG로만 (10Hz 폭주 방지). INFO는 throttle.
        log.debug("Vision 업데이트: %s", self.vision.to_context_string())
        now = time.monotonic()
        if now - self._last_vision_info_log >= VISION_LOG_THROTTLE_SEC:
            log.info("Vision 상태: %s", self.vision.to_context_string())
            self._last_vision_info_log = now

    async def _on_action_status(self, msg: dict) -> None:
        data = msg.get("data", {})
        status = data.get("status", "unknown")
        action_ref = data.get("action_ref", "")
        message = data.get("message", "")
        self.emit(f"[Action] {status} | {action_ref}: {message}")

    # -- 사용자 입력 처리 --

    async def handle_user_input(self, user_text: str) -> None:
        """사용자 텍스트 → LLM → robot_command 전송."""
        vision_context = self.vision.to_context_string()
        user_prompt = build_user_prompt(user_text, vision_context)

        self.emit("처리 중...")

        try:
            raw_response = await self.llm.chat(SYSTEM_PROMPT, user_prompt)
        except openai.AuthenticationError:
            self.emit("[오류] OpenAI API 키가 유효하지 않습니다. .env 파일을 확인하세요.")
            return
        except openai.RateLimitError:
            self.emit("[오류] OpenAI API 요청 한도 초과. 잠시 후 다시 시도하세요.")
            return
        except openai.APIConnectionError:
            self.emit("[오류] OpenAI API 서버에 연결할 수 없습니다. 네트워크를 확인하세요.")
            return
        except openai.APIError as exc:
            self.emit(f"[오류] OpenAI API 오류: {exc}")
            return

        response = parse_llm_response(raw_response, user_text)

        # 1. 일반 LLM 대화처럼 답변은 항상 출력
        self.emit(f"[답변] {response.answer.text}")
        if response.reasoning:
            self.emit(f"[근거] {response.reasoning}")

        # 2. 명령 의도가 없으면 종료 (순수 대화/질문)
        if response.command is None:
            return

        # 3. 명령이 있으면 처리
        command = response.command
        command.vision_confirmed = self.vision.has_label(command.target)

        # envelope 구성 후 전송 — Coordinator가 활성화된 경우에만.
        # 현재 Vision 직결합 단계에서는 송신 대상이 없으므로 파싱 결과를 stdout에만 출력한다.
        if not self.config.coordinator_enabled:
            self.emit(f"[명령 파싱] action={command.action.value}, "
                      f"target={command.target}, destination={command.destination}")
            self.emit(f"[근거] {command.reasoning}")
            self.emit("[명령 미전송 — 송신 대상 없음]")
            return

        envelope = {
            "type": TOPIC_ROBOT_COMMAND,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sender": SENDER_LANGUAGE,
            "data": command.model_dump(),
        }

        try:
            await self.hub.send(envelope)
        except (asyncio.TimeoutError, TimeoutError):
            self.emit("[오류] Coordinator에 연결되어 있지 않아 명령 전송에 실패했습니다.")
            return
        except Exception as exc:
            self.emit(f"[오류] 명령 전송 중 오류: {exc}")
            return

        self.emit(f"[명령 전송] action={command.action.value}, "
                  f"target={command.target}, destination={command.destination}")
        self.emit(f"[근거] {command.reasoning}")

    # -- 실행 --

    async def run(self) -> None:
        """WS 연결 + 사용자 입력 루프를 동시에 실행."""
        self.config.validate()

        print("=" * 50)
        print("PAI-Language 모듈")
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
