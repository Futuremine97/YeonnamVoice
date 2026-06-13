"""대화 엔진 추상화 (영어 회화 + 교정 + 모국어 설명).

프로토타입은 MockLLM(규칙 기반 응답). 실제는 Claude/OpenAI로 교체.
응답은 (reply_text, feedback) 형태.
"""
from abc import ABC, abstractmethod

from ..config import settings


def build_system_prompt(native_language: str, level: str) -> str:
    lang = {"ko": "Korean", "ja": "Japanese"}.get(native_language, "Korean")
    return (
        "You are a friendly English conversation tutor for a "
        f"{level}-level learner whose native language is {lang}. "
        "Hold a natural English conversation. After your reply, gently correct "
        "any grammar or word-choice mistakes in the learner's message, and add a "
        f"short explanation in {lang}. Keep replies concise and encouraging."
    )


class LLMEngine(ABC):
    @abstractmethod
    def reply(self, user_text: str, native_language: str, level: str) -> tuple[str, str]:
        ...


class MockLLM(LLMEngine):
    def reply(self, user_text: str, native_language: str, level: str) -> tuple[str, str]:
        reply = (
            "That's great! Tell me more about it. "
            "What did you do this weekend?"
        )
        if native_language == "ja":
            fb = "(添削) いい表現です。より自然には: \"I want to practice English.\""
        else:
            fb = "(교정) 좋아요! 더 자연스럽게는 \"I want to practice English.\" 처럼 말할 수 있어요."
        return reply, fb


class ClaudeLLM(LLMEngine):
    """Anthropic Claude 슬롯. EFU_ANTHROPIC_API_KEY 필요."""
    def reply(self, user_text: str, native_language: str, level: str) -> tuple[str, str]:
        from anthropic import Anthropic
        client = Anthropic(api_key=settings.anthropic_api_key)
        sys = build_system_prompt(native_language, level)
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=400,
            system=sys,
            messages=[{"role": "user", "content": user_text}],
        )
        text = msg.content[0].text
        # 데모 단순화: 전체를 reply로, 교정은 별도 호출 권장
        return text, ""


def get_llm() -> LLMEngine:
    if settings.llm_engine == "claude" and settings.anthropic_api_key:
        return ClaudeLLM()
    return MockLLM()
