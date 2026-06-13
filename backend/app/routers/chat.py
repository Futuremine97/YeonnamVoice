"""대화 엔드포인트: 모더레이션 → LLM → TTS(동의된 목소리) → 응답."""
import os

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .. import models, schemas
from ..config import settings
from ..database import get_db
from ..services import moderation
from ..services.llm import get_llm
from ..services.tts import get_tts
from ..services.stt import get_stt

router = APIRouter(prefix="/chat", tags=["chat"])


def _log(db: Session, event: str, **kw):
    db.add(models.AuditLog(event=event, **kw))


def _user_can_use(db: Session, user_id: str, voice: models.Voice) -> bool:
    """사용 권한: 직접 소유 또는 구매(보유권) 보유."""
    if voice.owner_id == user_id:
        return True
    return db.query(models.Entitlement).filter(
        models.Entitlement.user_id == user_id,
        models.Entitlement.voice_id == voice.id,
        models.Entitlement.active == True,  # noqa: E712
    ).first() is not None


def _resolve_active_voice(db: Session, user_id: str, voice_id: str | None) -> models.Voice | None:
    if not voice_id:
        return None
    voice = db.get(models.Voice, voice_id)
    if not voice or voice.status != models.VoiceStatus.ACTIVE:
        raise HTTPException(
            403, "활성화(동의 완료)된 음성이 아닙니다. 음성 등록·동의를 먼저 완료하세요."
        )
    if not _user_can_use(db, user_id, voice):
        raise HTTPException(
            402, "이 목소리는 구매 후 사용할 수 있습니다. 스토어에서 구매해 주세요."
        )
    return voice


@router.post("", response_model=schemas.ChatOut)
def chat(payload: schemas.ChatIn, db: Session = Depends(get_db)):
    user = db.get(models.User, payload.user_id)
    if not user:
        raise HTTPException(404, "user not found")

    # 1) 입력 모더레이션 (합성 이전 차단)
    mod = moderation.moderate_input(payload.text)
    if not mod.allowed:
        _log(db, "blocked", user_id=user.id, voice_id=payload.voice_id,
             detail=f"category={mod.category}")
        db.add(models.Message(user_id=user.id, role="user", text=payload.text))
        db.commit()
        return schemas.ChatOut(
            reply_text="", blocked=True,
            block_reason=mod.message, feedback=None,
        )

    voice = _resolve_active_voice(db, user.id, payload.voice_id)

    # 2) 대화 생성
    reply_text, feedback = get_llm().reply(
        payload.text, user.native_language, user.level
    )

    db.add(models.Message(user_id=user.id, role="user", text=payload.text))

    audio_url = None
    if voice:
        # 3) 레이트 리밋
        if not moderation.check_rate_limit(voice.id):
            raise HTTPException(429, "합성 한도를 초과했습니다. 잠시 후 다시 시도하세요.")
        # 4) 복제 목소리로 합성 (워터마크 메타데이터 자동 부착)
        audio_path = get_tts().synthesize(reply_text, voice.embedding_path, voice.id)
        audio_url = f"/chat/audio/{os.path.basename(audio_path)}"
        _log(db, "synthesized", user_id=user.id, voice_id=voice.id)

    db.add(models.Message(
        user_id=user.id, voice_id=payload.voice_id, role="assistant",
        text=reply_text, audio_path=audio_url, feedback=feedback,
    ))
    db.commit()

    return schemas.ChatOut(
        reply_text=reply_text, feedback=feedback, audio_url=audio_url,
    )


@router.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    """학습자 음성 → 텍스트 (Whisper 슬롯, 프로토타입은 mock)."""
    tmp = os.path.join(settings.data_dir, "tmp_" + (file.filename or "in.wav"))
    with open(tmp, "wb") as f:
        f.write(await file.read())
    text = get_stt().transcribe(tmp)
    os.remove(tmp)
    return {"text": text}


@router.get("/audio/{name}")
def get_audio(name: str):
    path = os.path.join(settings.audio_out_dir, name)
    if not os.path.exists(path):
        raise HTTPException(404, "audio not found")
    return FileResponse(path, media_type="audio/wav")
