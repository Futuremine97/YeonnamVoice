"""악용방지: 입력 모더레이션 + 레이트리밋.

프로토타입은 규칙 기반. 고도화 시 LLM/전용 모더레이션 API로 2차 판정 추가.
"""
import re
import time
from dataclasses import dataclass
from typing import Optional

from ..config import settings


@dataclass
class ModerationResult:
    allowed: bool
    category: Optional[str] = None
    message: Optional[str] = None  # 사용자 안내 (차단 시)


# 카테고리별 패턴 (간략 데모용; 운영 시 확장·다국어·LLM 보강)
_PATTERNS = {
    "impersonation": [
        r"pretend (to be|you are)\s+\w+",
        r"act as (the )?(president|ceo|celebrity|\w+ trump|\w+ musk)",
        r"(흉내|사칭|인 척).{0,10}(말해|해줘)",
        r"なりきっ|のふりをして",
    ],
    "hate_harassment": [
        r"\b(kill|hurt|threaten)\s+(you|him|her|them)\b",
        r"\b(racial slur|ethnic slur)\b",
    ],
    "minor_sexual": [
        r"\b(child|minor|underage)\b.{0,20}\b(sex|nude|naked)\b",
    ],
    "fraud": [
        r"\b(phishing|scam script|wire transfer|bank password|otp code)\b",
        r"(피싱|보이스피싱|송금).{0,10}(대본|스크립트)",
    ],
}

_SELF_HARM = [
    r"\b(kill myself|suicide|end my life|self[- ]harm)\b",
    r"(자살|죽고 싶|자해)",
]

_SELF_HARM_MSG = (
    "힘든 마음이 느껴집니다. 이 주제는 민감해서 음성 합성으로는 다루지 않습니다. "
    "지금 많이 괴롭다면 혼자 견디지 말고 가까운 사람이나 전문가의 도움을 받아보세요. "
    "원하시면 도움받을 수 있는 자원을 함께 찾아볼 수 있습니다."
)

_BLOCK_MSGS = {
    "impersonation": "특정 인물 사칭·흉내 요청은 처리할 수 없습니다. 사칭은 약관에서 금지됩니다.",
    "hate_harassment": "혐오·위협·괴롭힘에 해당하는 요청은 처리할 수 없습니다.",
    "minor_sexual": "미성년자 관련 부적절한 요청은 처리할 수 없습니다.",
    "fraud": "사기·피싱 등 불법 목적의 요청은 처리할 수 없습니다.",
}


def moderate_input(text: str) -> ModerationResult:
    low = text.lower()
    for pat in _SELF_HARM:
        if re.search(pat, low) or re.search(pat, text):
            return ModerationResult(False, "self_harm", _SELF_HARM_MSG)
    for category, patterns in _PATTERNS.items():
        for pat in patterns:
            if re.search(pat, low) or re.search(pat, text):
                return ModerationResult(False, category, _BLOCK_MSGS[category])
    return ModerationResult(True)


# ---- 레이트 리밋 (메모리 기반; 운영 시 Redis) ----
_synth_log: dict[str, list[float]] = {}


def check_rate_limit(voice_id: str) -> bool:
    """voice별 시간당 합성 횟수 제한. 초과 시 False."""
    now = time.time()
    window = 3600
    hist = [t for t in _synth_log.get(voice_id, []) if now - t < window]
    if len(hist) >= settings.max_synth_per_voice_per_hour:
        _synth_log[voice_id] = hist
        return False
    hist.append(now)
    _synth_log[voice_id] = hist
    return True
