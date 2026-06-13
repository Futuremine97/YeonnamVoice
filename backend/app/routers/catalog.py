"""음성 마켓플레이스: 목소리 공개(판매등록) · 카탈로그 · 구매."""
import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..services.payments import get_payments

router = APIRouter(prefix="/catalog", tags=["catalog"])


def _log(db: Session, event: str, **kw):
    db.add(models.AuditLog(event=event, **kw))


def _has_entitlement(db: Session, user_id: str, voice_id: str) -> bool:
    return db.query(models.Entitlement).filter(
        models.Entitlement.user_id == user_id,
        models.Entitlement.voice_id == voice_id,
        models.Entitlement.active == True,  # noqa: E712
    ).first() is not None


@router.post("/voices/{voice_id}/publish", response_model=schemas.CatalogItem)
def publish_voice(voice_id: str, payload: schemas.VoicePublish, db: Session = Depends(get_db)):
    """동의 완료(ACTIVE)된 목소리만 스토어에 판매 등록할 수 있다."""
    voice = db.get(models.Voice, voice_id)
    if not voice or voice.status != models.VoiceStatus.ACTIVE:
        raise HTTPException(403, "ACTIVE(동의 완료) 상태의 음성만 판매 등록할 수 있습니다.")
    if payload.price_cents < 0:
        raise HTTPException(422, "가격은 0 이상이어야 합니다.")
    voice.is_listed = True
    voice.price_cents = payload.price_cents
    voice.accent = payload.accent
    voice.gender = payload.gender
    voice.description = payload.description
    _log(db, "voice_listed", user_id=voice.owner_id, voice_id=voice.id,
         detail=f"price={payload.price_cents}")
    db.commit()
    db.refresh(voice)
    return schemas.CatalogItem.model_validate(voice)


@router.get("/voices", response_model=list[schemas.CatalogItem])
def list_catalog(user_id: str | None = None, accent: str | None = None,
                 db: Session = Depends(get_db)):
    """판매 중인 원어민 목소리 카탈로그. user_id 주면 보유 여부 표시."""
    q = db.query(models.Voice).filter(
        models.Voice.is_listed == True,  # noqa: E712
        models.Voice.status == models.VoiceStatus.ACTIVE,
    )
    if accent:
        q = q.filter(models.Voice.accent == accent)
    items = []
    for v in q.all():
        item = schemas.CatalogItem.model_validate(v)
        if user_id:
            item.owned = (v.owner_id == user_id) or _has_entitlement(db, user_id, v.id)
        items.append(item)
    return items


@router.post("/voices/{voice_id}/purchase", response_model=schemas.OrderOut)
def purchase(voice_id: str, payload: schemas.PurchaseIn, db: Session = Depends(get_db)):
    """구매 시작: 주문 생성 + 결제 인텐트. 결제 확정은 /orders/{id}/confirm."""
    user = db.get(models.User, payload.user_id)
    voice = db.get(models.Voice, voice_id)
    if not user:
        raise HTTPException(404, "user not found")
    if not voice or not voice.is_listed or voice.status != models.VoiceStatus.ACTIVE:
        raise HTTPException(404, "구매 가능한 음성이 아닙니다.")
    if voice.owner_id == payload.user_id or _has_entitlement(db, payload.user_id, voice_id):
        raise HTTPException(409, "이미 보유한 음성입니다.")

    order = models.Order(
        user_id=user.id, voice_id=voice.id,
        amount_cents=voice.price_cents, status=models.OrderStatus.PENDING,
    )
    db.add(order)
    db.flush()

    pay = get_payments()
    ref, token = pay.create_intent(voice.price_cents, "usd", order.id)
    order.provider = pay.name
    order.provider_ref = ref
    _log(db, "order_created", user_id=user.id, voice_id=voice.id,
         detail=f"order={order.id} amount={voice.price_cents}")
    db.commit()
    db.refresh(order)
    return schemas.OrderOut(
        order_id=order.id, status=order.status.value,
        amount_cents=order.amount_cents, currency=order.currency,
        payment_token=token,
    )


@router.post("/orders/{order_id}/confirm", response_model=schemas.OrderOut)
def confirm_order(order_id: str, payment_token: str, db: Session = Depends(get_db)):
    """결제 확정 → 보유권(Entitlement) 부여."""
    order = db.get(models.Order, order_id)
    if not order:
        raise HTTPException(404, "order not found")
    if order.status == models.OrderStatus.PAID:
        return schemas.OrderOut(order_id=order.id, status=order.status.value,
                                amount_cents=order.amount_cents, currency=order.currency)

    ok = get_payments().confirm(order.provider_ref, payment_token)
    if not ok:
        order.status = models.OrderStatus.FAILED
        _log(db, "payment_failed", user_id=order.user_id, voice_id=order.voice_id,
             detail=f"order={order.id}")
        db.commit()
        raise HTTPException(402, "결제 확정에 실패했습니다.")

    order.status = models.OrderStatus.PAID
    order.paid_at = dt.datetime.utcnow()
    ent = models.Entitlement(user_id=order.user_id, voice_id=order.voice_id,
                             order_id=order.id, active=True)
    db.add(ent)
    _log(db, "entitlement_granted", user_id=order.user_id, voice_id=order.voice_id,
         detail=f"order={order.id}")
    db.commit()
    db.refresh(order)
    return schemas.OrderOut(order_id=order.id, status=order.status.value,
                            amount_cents=order.amount_cents, currency=order.currency)


@router.get("/my-voices", response_model=list[schemas.CatalogItem])
def my_voices(user_id: str, db: Session = Depends(get_db)):
    """사용자가 사용할 수 있는 목소리: 직접 소유 + 구매한 것."""
    owned_ids = {
        e.voice_id for e in db.query(models.Entitlement).filter(
            models.Entitlement.user_id == user_id,
            models.Entitlement.active == True,  # noqa: E712
        ).all()
    }
    own = db.query(models.Voice).filter(
        models.Voice.owner_id == user_id,
        models.Voice.status == models.VoiceStatus.ACTIVE,
    ).all()
    owned_ids.update(v.id for v in own)

    out = []
    for vid in owned_ids:
        v = db.get(models.Voice, vid)
        if v and v.status == models.VoiceStatus.ACTIVE:
            item = schemas.CatalogItem.model_validate(v)
            item.owned = True
            out.append(item)
    return out
