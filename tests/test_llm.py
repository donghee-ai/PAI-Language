"""LLM 파이프라인 단독 테스트 — WS 연결 없이 자연어 → 구조화 명령 확인.

실행: python -m tests.test_llm
"""

from __future__ import annotations

import asyncio
import json

from language.config import Config
from language.context.vision_state import VisionState
from language.llm.openai_client import LLMClient
from language.llm.prompt_builder import SYSTEM_PROMPT, build_user_prompt
from language.llm.response_parser import parse_llm_response

# 테스트용 더미 vision 데이터
DUMMY_VISION = {
    "objects": [
        {"label": "ball", "center_pixel": [640, 360], "confidence": 0.91, "status": "tracked"},
        {"label": "basket", "center_pixel": [900, 400], "confidence": 0.87, "status": "tracked"},
    ]
}


async def main() -> None:
    config = Config()
    config.validate()

    llm = LLMClient(config)
    vision = VisionState()
    vision.update(DUMMY_VISION)

    print("=" * 50)
    print("LLM 파이프라인 테스트 (WS 없음)")
    print(f"  모델: {config.openai_model}")
    print(f"  비전: {vision.to_context_string()}")
    print("  종료: quit / exit / Ctrl+C")
    print("=" * 50)

    while True:
        try:
            user_text = input("\n> ").strip()
            if not user_text or user_text.lower() in ("quit", "exit", "q"):
                break

            vision_context = vision.to_context_string()
            user_prompt = build_user_prompt(user_text, vision_context)

            print("\n[프롬프트]")
            print(user_prompt)
            print("처리 중...")

            raw = await llm.chat(SYSTEM_PROMPT, user_prompt)

            print(f"\n[LLM 원본 응답]\n{raw}")

            response = parse_llm_response(raw, user_text)

            print(f"\n[답변] {response.answer.text}")
            if response.reasoning:
                print(f"[근거] {response.reasoning}")
            if response.command is not None:
                print("\n[명령 파싱 결과]")
                print(json.dumps(response.command.model_dump(), indent=2, ensure_ascii=False))
            else:
                print("\n[명령 없음 — 일반 대화/질문]")

        except (EOFError, KeyboardInterrupt):
            break

    print("종료.")


if __name__ == "__main__":
    asyncio.run(main())
