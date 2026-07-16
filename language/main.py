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
    STOP_TASK_INSTRUCTION,
    TOPIC_ACTION_STATUS,
    TOPIC_ROBOT_COMMAND,
    TOPIC_VISION_UPDATE,
    TRASH_TASK_INSTRUCTION,
)
from shared.schemas.command import ActionType, RobotCommand
from language.config import Config
from language.context.vision_state import VisionState
from language.input.cli_handler import input_loop
from language.llm.openai_client import LLMClient
from language.llm.prompt_builder import SYSTEM_PROMPT, build_user_prompt
from language.llm.response_parser import parse_llm_response
from language.ws.client import HubClient
from language.ws.dispatcher import Dispatcher
from language.zmq_pub.instruction_publisher import InstructionPublisher

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
        self.instruction_publisher = (
            InstructionPublisher(bind_address=config.instruction_pub_bind)
            if config.instruction_pub_enabled
            else None
        )
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
        # 0. 정지 의도 — LLM 왕복 없이 최우선 처리(즉각성). 실행 중이던 ACT 롤아웃을
        #    즉시 멈추고 초기 대기 자세로 복귀시킨다. rollout 어댑터가 STOP_TASK_INSTRUCTION
        #    을 받으면 executing=False + engine.reset()(ACT 큐 비우기)을 수행한다.
        if self._is_stop_intent(user_text):
            self._publish_stop(user_text)
            return

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

        # 2. 로봇 실행 게이트 — 현재 붙은 LeRobot 정책은 ACT(`act-trash-gathering-danny`)로
        #    '쓰레기 모으기' 단일 태스크만 수행하며 instruction '내용'으로 행동이 바뀌지 않는다.
        #    따라서 "말 → 로봇 실행"의 의미 판단은 Language가 맡는다: 사용자 입력이
        #    쓰레기-모으기 의도(키워드 포함)일 때만 5557로 트리거를 발행하고, 그 외 입력은
        #    LLM 대화 답변만 하고 로봇을 건드리지 않는다.
        if not self._is_trash_intent(user_text):
            # LLM이 명령을 파싱했더라도 쓰레기 모으기 의도가 아니면 로봇은 실행하지 않는다.
            if response.command is not None:
                c = response.command
                self.emit(
                    f"[명령 파싱] action={c.action.value}, target={c.target}, "
                    f"destination={c.destination} — 쓰레기 모으기 의도가 아니라 미실행"
                )
            return

        # 3. 쓰레기-모으기 의도 확정 → LeRobot 트리거 발행.
        #    instruction 은 학습 task 명("trash_gathering")과 일치시켜 rollout 어댑터가
        #    engine._task 로 주입하는 값이 학습 분포와 어긋나지 않게 한다.
        command = RobotCommand(
            action=ActionType.TRASH_GATHER,
            instruction=TRASH_TASK_INSTRUCTION,
            raw_input=user_text,
            reasoning="쓰레기 모으기 의도 키워드 감지",
            vision_confirmed=True,
        )

        published = False
        if self.instruction_publisher is not None:
            published = self.instruction_publisher.publish(command)

        self.emit(f"[쓰레기 모으기 감지] instruction={command.instruction!r}")
        if published:
            self.emit(f"[ZMQ 발행 → LeRobot] {self.config.instruction_pub_bind}")
        else:
            self.emit(
                "[미발행 — instruction publisher 비활성] "
                ".env 의 INSTRUCTION_PUB_ENABLED=1 및 pyzmq 설치를 확인하세요."
            )

    def _is_trash_intent(self, user_text: str) -> bool:
        """사용자 입력에 쓰레기-모으기 의도 키워드가 하나라도 포함됐는지."""
        text = user_text.lower()
        return any(kw.lower() in text for kw in self.config.trash_keywords)

    def _is_stop_intent(self, user_text: str) -> bool:
        """사용자 입력에 정지 의도 키워드가 하나라도 포함됐는지."""
        text = user_text.lower()
        return any(kw.lower() in text for kw in self.config.stop_keywords)

    def _publish_stop(self, user_text: str) -> None:
        """정지 트리거를 LeRobot 으로 발행. 실행 중이면 즉시 정지 + ACT 큐 비우기.

        instruction 은 STOP_TASK_INSTRUCTION("stop") 고정 — rollout 어댑터가 이 값을
        보고 실행 창 종료 + engine.reset() 을 수행한다. STOP 액션은 target/destination
        이 불필요하다(스키마 validator 가 강제로 none 처리).
        """
        command = RobotCommand(
            action=ActionType.STOP,
            instruction=STOP_TASK_INSTRUCTION,
            raw_input=user_text,
            reasoning="정지 의도 키워드 감지",
            vision_confirmed=True,
        )

        published = False
        if self.instruction_publisher is not None:
            published = self.instruction_publisher.publish(command)

        self.emit(f"[정지 감지] instruction={command.instruction!r} — 즉시 정지 + ACT 큐 비우기")
        if published:
            self.emit(f"[ZMQ 발행 → LeRobot] {self.config.instruction_pub_bind}")
        else:
            self.emit(
                "[미발행 — instruction publisher 비활성] "
                ".env 의 INSTRUCTION_PUB_ENABLED=1 및 pyzmq 설치를 확인하세요."
            )

    # -- 실행 --

    # -- 백그라운드 서비스 라이프사이클 --
    #
    # CLI(main)/UI 양쪽에서 동일하게 호출하기 위해 분리. CLI 는 run() 안에서 start/stop,
    # UI 는 자기 라이프사이클(생성/종료)에서 직접 호출한다.

    def start_services(self) -> None:
        if self.instruction_publisher is not None:
            self.instruction_publisher.start()

    def stop_services(self) -> None:
        if self.instruction_publisher is not None:
            self.instruction_publisher.stop()

    async def run(self) -> None:
        """WS 연결 + 사용자 입력 루프를 동시에 실행."""
        self.config.validate()
        self.start_services()

        print("=" * 50)
        print("PAI-Language 모듈")
        print(f"  WS:  {self.config.ws_url}")
        print(f"  LLM: {self.config.openai_model}")
        if self.instruction_publisher is not None and self.instruction_publisher.enabled:
            print(f"  ZMQ instruction PUB → LeRobot: {self.config.instruction_pub_bind}")
        print("  종료: quit / exit / Ctrl+C")
        print("=" * 50)

        ws_task = asyncio.create_task(self.hub.run())
        input_task = asyncio.create_task(input_loop(self.handle_user_input))

        try:
            # 입력 루프가 끝나면(사용자가 quit) 전체 종료
            done, pending = await asyncio.wait(
                [ws_task, input_task],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for t in pending:
                t.cancel()
        finally:
            self.stop_services()


def main() -> None:
    config = Config()
    app = LanguageApp(config)
    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        print("\n종료됨.")


if __name__ == "__main__":
    main()
