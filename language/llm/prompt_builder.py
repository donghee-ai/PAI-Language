"""user_input + vision_context → OpenAI 프롬프트 조합."""

from __future__ import annotations

SYSTEM_PROMPT = """\
당신은 로봇 팔 제어 명령을 생성하는 AI입니다.
사용자의 자연어 명령과 카메라 감지 정보를 기반으로, 아래 JSON 형식의 로봇 명령을 생성하세요.

## 출력 형식 (반드시 JSON만 출력)
{
  "action": "pick" | "place" | "pick_and_place" | "home" | "stop",
  "target": "<YOLO 라벨 또는 none>",
  "destination": "<YOLO 라벨 또는 none>",
  "reasoning": "<한 문장 판단 근거>"
}

## 규칙
1. action="pick" → target ≠ "none"
2. action="place" → target ≠ "none", destination ≠ "none"
3. action="pick_and_place" → target ≠ "none", destination ≠ "none"
4. action="home" 또는 "stop" → target="none", destination="none"
5. 모호하거나 위험한 명령 → action="stop"
6. 카메라에 해당 객체가 없으면 가장 합리적인 판단을 하되, 반드시 reasoning에 명시

JSON 외의 텍스트는 출력하지 마세요.
"""


def build_user_prompt(user_text: str, vision_context: str) -> str:
    """사용자 입력과 비전 컨텍스트를 합쳐 유저 프롬프트를 만든다."""
    return f"""\
[카메라 상태]
{vision_context}

[사용자 명령]
{user_text}
"""
