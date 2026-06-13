"""애플리케이션 설정.

환경변수로 실제 엔진(OpenAI/Anthropic/Chatterbox)을 켤 수 있다.
키가 없으면 mock 어댑터로 동작하므로 프로토타입이 그대로 실행된다.
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "English For Us API"
    consent_version: str = "2026-06-13"  # 동의 약관 버전 (증빙용)

    # 저장 경로
    data_dir: str = "./data"
    voice_dir: str = "./data/voices"
    audio_out_dir: str = "./data/generated"

    # 외부 엔진 (없으면 mock)
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    tts_engine: str = "mock"   # mock | chatterbox
    stt_engine: str = "mock"   # mock | whisper
    llm_engine: str = "mock"   # mock | claude | openai

    # 악용방지
    max_synth_per_voice_per_hour: int = 60

    class Config:
        env_file = ".env"
        env_prefix = "EFU_"


settings = Settings()
