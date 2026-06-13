"""Pydantic 요청/응답 스키마."""
from typing import Optional
from pydantic import BaseModel


class UserCreate(BaseModel):
    email: str
    native_language: str = "ko"
    level: str = "intermediate"


class UserOut(BaseModel):
    id: str
    email: str
    native_language: str
    level: str

    class Config:
        from_attributes = True


class ConsentIn(BaseModel):
    owns_or_authorized: bool = False
    purpose_limited: bool = False
    no_impersonation: bool = False
    not_minor: bool = False
    accepted_terms: bool = False


class VoiceOut(BaseModel):
    id: str
    display_name: str
    status: str
    sample_seconds: int

    class Config:
        from_attributes = True


class VoicePublish(BaseModel):
    price_cents: int = 0
    accent: str = "American"
    gender: str = "unspecified"
    description: Optional[str] = None


class CatalogItem(BaseModel):
    id: str
    display_name: str
    accent: str
    gender: str
    description: Optional[str] = None
    price_cents: int
    sample_seconds: int
    owned: bool = False  # 요청 사용자의 보유 여부

    class Config:
        from_attributes = True


class PurchaseIn(BaseModel):
    user_id: str


class OrderOut(BaseModel):
    order_id: str
    status: str
    amount_cents: int
    currency: str
    # mock 결제 확정에 쓰는 클라이언트 토큰 (실서비스는 Stripe client_secret 등)
    payment_token: Optional[str] = None


class ChatIn(BaseModel):
    user_id: str
    voice_id: Optional[str] = None
    text: str


class ChatOut(BaseModel):
    reply_text: str
    feedback: Optional[str] = None
    audio_url: Optional[str] = None
    blocked: bool = False
    block_reason: Optional[str] = None
