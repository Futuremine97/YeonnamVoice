"""TTS 엔진 추상화.

Chatterbox/F5-TTS/XTTS를 코드 변경 최소화로 교체할 수 있도록 인터페이스 뒤로 숨긴다.
프로토타입은 MockTTS (오디오 대신 마커 파일 생성 + 합성 메타데이터 기록).
"""
import datetime as dt
import json
import os
import uuid
from abc import ABC, abstractmethod

from ..config import settings


class TTSEngine(ABC):
    @abstractmethod
    def synthesize(self, text: str, embedding_path: str | None, voice_id: str) -> str:
        """텍스트 -> 오디오 파일 경로. 합성 워터마크 메타데이터를 함께 남긴다."""
        ...


def _write_watermark(audio_path: str, voice_id: str, text: str):
    """모든 합성물에 식별 메타데이터(워터마크)를 남겨 추적 가능하게 한다."""
    meta = {
        "synthetic": True,
        "service": "english_for_us",
        "voice_id": voice_id,
        "generated_at": dt.datetime.utcnow().isoformat(),
        "text_preview": text[:80],
    }
    with open(audio_path + ".meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


class MockTTS(TTSEngine):
    def synthesize(self, text: str, embedding_path: str | None, voice_id: str) -> str:
        os.makedirs(settings.audio_out_dir, exist_ok=True)
        name = f"{voice_id}_{uuid.uuid4().hex[:8]}.wav"
        path = os.path.join(settings.audio_out_dir, name)
        # 실제 오디오 대신 플레이스홀더. 실엔진 연동 시 이 부분만 교체.
        with open(path, "wb") as f:
            f.write(b"RIFF....MOCK_AUDIO...." + text[:40].encode("utf-8", "ignore"))
        _write_watermark(path, voice_id, text)
        return path


class ChatterboxTTS(TTSEngine):
    """실엔진 슬롯. resemble chatterbox 설치 후 구현.

    예:
        from chatterbox import ChatterboxTTS as CB
        wav = CB.tts(text, reference_audio=embedding_path)
    """
    def synthesize(self, text: str, embedding_path: str | None, voice_id: str) -> str:
        raise NotImplementedError(
            "Chatterbox 미설치. EFU_TTS_ENGINE=mock 으로 실행하거나 엔진을 구현하세요."
        )


def get_tts() -> TTSEngine:
    if settings.tts_engine == "chatterbox":
        return ChatterboxTTS()
    return MockTTS()
