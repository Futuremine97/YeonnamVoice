"""STT 엔진 추상화 (학습자 발화 인식).

프로토타입은 MockSTT. 실제는 OpenAI Whisper API 등으로 교체.
"""
from abc import ABC, abstractmethod

from ..config import settings


class STTEngine(ABC):
    @abstractmethod
    def transcribe(self, audio_path: str) -> str:
        ...


class MockSTT(STTEngine):
    def transcribe(self, audio_path: str) -> str:
        return "(mock transcription) Hello, I want to practice English today."


class WhisperSTT(STTEngine):
    """OpenAI Whisper API 슬롯. EFU_OPENAI_API_KEY 필요."""
    def transcribe(self, audio_path: str) -> str:
        from openai import OpenAI
        client = OpenAI(api_key=settings.openai_api_key)
        with open(audio_path, "rb") as f:
            r = client.audio.transcriptions.create(model="whisper-1", file=f)
        return r.text


def get_stt() -> STTEngine:
    if settings.stt_engine == "whisper" and settings.openai_api_key:
        return WhisperSTT()
    return MockSTT()
