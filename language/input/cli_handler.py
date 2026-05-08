"""asyncio 기반 stdin 입력 핸들러."""

from __future__ import annotations

import asyncio
import logging

log = logging.getLogger(__name__)


async def read_user_input(prompt: str = "> ") -> str:
    """비동기로 한 줄의 사용자 입력을 읽어 반환한다."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: input(prompt))


async def input_loop(on_input):
    """사용자 입력을 반복적으로 읽어 콜백에 전달한다.

    Args:
        on_input: async callable(user_text: str) → None
    """
    while True:
        try:
            text = await read_user_input()
            text = text.strip()
            if not text:
                continue
            if text.lower() in ("quit", "exit", "q"):
                print("종료합니다.")
                break
            await on_input(text)
        except (EOFError, KeyboardInterrupt):
            print("\n종료합니다.")
            break
