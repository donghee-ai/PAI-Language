"""OpenAI API 비동기 래퍼."""

from __future__ import annotations

import logging

from openai import AsyncOpenAI

from language.config import Config

log = logging.getLogger(__name__)


class LLMClient:
    """OpenAI Chat Completion 비동기 호출."""

    def __init__(self, config: Config) -> None:
        self._client = AsyncOpenAI(api_key=config.openai_api_key)
        self._model = config.openai_model

    async def chat(self, system_prompt: str, user_prompt: str) -> str:
        """시스템 + 유저 프롬프트를 보내고 응답 텍스트를 반환."""
        log.debug("LLM 요청: model=%s", self._model)
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
        )
        content = response.choices[0].message.content or ""
        log.debug("LLM 응답: %s", content[:200])
        return content
