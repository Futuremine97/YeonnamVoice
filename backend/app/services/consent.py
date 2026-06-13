"""동의 처리: 동의 기록 생성, 검증, 상태 전이."""
import datetime as dt
import hashlib
import json

from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from ..schemas import ConsentIn


def _hash_consent(voice_id: str, data: ConsentIn, when: str) -> str:
    payload = json.dumps(
        {"voice_id": voice_id, **data.model_dump(), "when": when,
         "version": settings.consent_version},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def record_consent(db: Session, voice: models.Voice, data: ConsentIn) -> models.ConsentRecord:
    when = dt.datetime.utcnow().isoformat()
    rec = models.ConsentRecord(
        voice_id=voice.id,
        owns_or_authorized=data.owns_or_authorized,
        purpose_limited=data.purpose_limited,
        no_impersonation=data.no_impersonation,
        not_minor=data.not_minor,
        accepted_terms=data.accepted_terms,
        consent_version=settings.consent_version,
        consent_hash=_hash_consent(voice.id, data, when),
    )
    db.add(rec)
    return rec


def all_required_granted(data: ConsentIn) -> bool:
    return all([
        data.owns_or_authorized,
        data.purpose_limited,
        data.no_impersonation,
        data.not_minor,
        data.accepted_terms,
    ])
