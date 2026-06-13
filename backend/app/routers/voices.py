"""음성 등록 · 동의 게이트 · 삭제."""
import datetime as dt
import json
import os

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from .. import models, schemas
from ..config import settings
from ..database import get_db
from ..services import consent as consent_svc

router = APIRouter(prefix="/voices", tags=["voices"])


def _log(db: Session, event: str, **kw):
    db.add(models.AuditLog(event=event, **kw))


@router.post("", response_model=schemas.VoiceOut)
async def register_voice(
    user_id: str = Form(...),
    display_name: str = Form(...),
    consent: str = Form(...),  # JSON 문자열
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """음성 업로드 + 동의. 동의 5개 항목 모두 통과해야 ACTIVE 후보가 된다."""
    user = db.get(models.User, user_id)
    if not user:
        raise HTTPException(404, "user not found")

    try:
        consent_in = schemas.ConsentIn(**json.loads(consent))
    except Exception:
        raise HTTPException(422, "invalid consent payload")

    voice = models.Voice(
        owner_id=user_id,
        display_name=display_name,
        status=models.VoiceStatus.PENDING_CONSENT,
    )
    db.add(voice)
    db.flush()  # voice.id 확보

    # 동의 기록은 항상 남긴다 (거부 케이스도 증빙)
    consent_svc.record_consent(db, voice, consent_in)

    # 동의 게이트: 하나라도 미동의면 거부
    if not consent_svc.all_required_granted(consent_in):
        voice.status = models.VoiceStatus.REJECTED
        _log(db, "consent_rejected", user_id=user_id, voice_id=voice.id,
             detail="필수 동의 항목 누락")
        db.commit()
        raise HTTPException(
            403,
            "필수 동의 항목에 모두 동의해야 음성을 등록할 수 있습니다 "
            "(본인/권한, 목적제한, 사칭금지, 미성년자아님, 약관).",
        )

    # 파일 저장
    os.makedirs(settings.voice_dir, exist_ok=True)
    raw = await file.read()
    src_path = os.path.join(settings.voice_dir, f"{voice.id}.bin")
    with open(src_path, "wb") as f:
        f.write(raw)
    voice.source_path = src_path
    # 데모: 길이 추정 (실제는 오디오 디코딩). 바이트로 근사.
    voice.sample_seconds = max(1, len(raw) // 16000)

    # 동의 통과 → 검증/지문화 (프로토타입은 즉시 지문 생성 후 ACTIVE)
    voice.status = models.VoiceStatus.VERIFYING
    emb_path = os.path.join(settings.voice_dir, f"{voice.id}.embedding.json")
    with open(emb_path, "w", encoding="utf-8") as f:
        json.dump({"voice_id": voice.id, "note": "mock speaker embedding"}, f)
    voice.embedding_path = emb_path
    voice.status = models.VoiceStatus.ACTIVE

    _log(db, "consent_granted", user_id=user_id, voice_id=voice.id,
         detail=f"version={settings.consent_version}")
    _log(db, "voice_activated", user_id=user_id, voice_id=voice.id)
    db.commit()
    db.refresh(voice)
    return voice


@router.get("/{voice_id}", response_model=schemas.VoiceOut)
def get_voice(voice_id: str, db: Session = Depends(get_db)):
    voice = db.get(models.Voice, voice_id)
    if not voice or voice.status == models.VoiceStatus.DELETED:
        raise HTTPException(404, "voice not found")
    return voice


@router.delete("/{voice_id}")
def delete_voice(voice_id: str, db: Session = Depends(get_db)):
    """완전 삭제: 원본·지문·생성물 제거 + 감사 로그."""
    voice = db.get(models.Voice, voice_id)
    if not voice or voice.status == models.VoiceStatus.DELETED:
        raise HTTPException(404, "voice not found")

    for p in [voice.source_path, voice.embedding_path]:
        if p and os.path.exists(p):
            os.remove(p)
    # 생성 오디오 제거
    if os.path.isdir(settings.audio_out_dir):
        for fn in os.listdir(settings.audio_out_dir):
            if fn.startswith(voice_id):
                os.remove(os.path.join(settings.audio_out_dir, fn))

    voice.status = models.VoiceStatus.DELETED
    voice.deleted_at = dt.datetime.utcnow()
    voice.source_path = None
    voice.embedding_path = None
    _log(db, "voice_deleted", user_id=voice.owner_id, voice_id=voice.id,
         detail="원본·지문·생성물 완전 삭제")
    db.commit()
    return {"deleted": True, "voice_id": voice_id}
