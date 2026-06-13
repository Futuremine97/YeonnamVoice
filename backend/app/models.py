"""데이터 모델: 사용자, 음성, 동의기록, 감사로그, 대화."""
import datetime as dt
import enum
import uuid

from sqlalchemy import (
    Column, String, Integer, DateTime, Boolean, Text, ForeignKey, Enum
)
from sqlalchemy.orm import relationship

from .database import Base


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> dt.datetime:
    return dt.datetime.utcnow()


class VoiceStatus(str, enum.Enum):
    PENDING_CONSENT = "PENDING_CONSENT"
    VERIFYING = "VERIFYING"
    ACTIVE = "ACTIVE"
    REJECTED = "REJECTED"
    DELETED = "DELETED"


class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, default=_uuid)
    email = Column(String, unique=True, index=True, nullable=False)
    native_language = Column(String, default="ko")  # ko | ja
    level = Column(String, default="intermediate")    # beginner|intermediate|advanced
    created_at = Column(DateTime, default=_now)

    voices = relationship("Voice", back_populates="owner")


class Voice(Base):
    __tablename__ = "voices"
    id = Column(String, primary_key=True, default=_uuid)
    owner_id = Column(String, ForeignKey("users.id"), nullable=False)
    display_name = Column(String, nullable=False)
    status = Column(Enum(VoiceStatus), default=VoiceStatus.PENDING_CONSENT)
    source_path = Column(String, nullable=True)       # 업로드 원본
    embedding_path = Column(String, nullable=True)    # 추출된 목소리 지문
    sample_seconds = Column(Integer, default=0)
    created_at = Column(DateTime, default=_now)
    deleted_at = Column(DateTime, nullable=True)

    # --- 마켓플레이스(원어민 목소리 프로필) ---
    is_listed = Column(Boolean, default=False)        # 스토어 공개 여부
    price_cents = Column(Integer, default=0)          # 판매가(센트, USD 기준 데모)
    accent = Column(String, default="American")       # American/British/Australian...
    gender = Column(String, default="unspecified")
    description = Column(Text, nullable=True)
    preview_path = Column(String, nullable=True)      # 미리듣기 샘플(워터마크)

    owner = relationship("User", back_populates="voices")
    consent = relationship("ConsentRecord", back_populates="voice", uselist=False)


class OrderStatus(str, enum.Enum):
    PENDING = "PENDING"      # 결제 대기
    PAID = "PAID"            # 결제 완료 → 보유권 부여
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


class Order(Base):
    """구매 주문 (결제 provider 슬롯; 프로토타입은 mock 결제)."""
    __tablename__ = "orders"
    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    voice_id = Column(String, ForeignKey("voices.id"), nullable=False)
    amount_cents = Column(Integer, default=0)
    currency = Column(String, default="usd")
    status = Column(Enum(OrderStatus), default=OrderStatus.PENDING)
    provider = Column(String, default="mock")
    provider_ref = Column(String, nullable=True)     # 결제 intent id 등
    created_at = Column(DateTime, default=_now)
    paid_at = Column(DateTime, nullable=True)


class Entitlement(Base):
    """보유권: 사용자가 특정 목소리를 사용할 권리. 구매 완료 시 생성."""
    __tablename__ = "entitlements"
    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    voice_id = Column(String, ForeignKey("voices.id"), nullable=False)
    order_id = Column(String, ForeignKey("orders.id"), nullable=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=_now)


class ConsentRecord(Base):
    """동의 증빙: 항목별 동의 여부 + 시각 + 약관 버전 + 해시."""
    __tablename__ = "consent_records"
    id = Column(String, primary_key=True, default=_uuid)
    voice_id = Column(String, ForeignKey("voices.id"), nullable=False)
    owns_or_authorized = Column(Boolean, default=False)
    purpose_limited = Column(Boolean, default=False)
    no_impersonation = Column(Boolean, default=False)
    not_minor = Column(Boolean, default=False)
    accepted_terms = Column(Boolean, default=False)
    consent_version = Column(String, nullable=False)
    consent_hash = Column(String, nullable=False)     # 항목+시각 해시
    created_at = Column(DateTime, default=_now)

    voice = relationship("Voice", back_populates="consent")

    REQUIRED = [
        "owns_or_authorized",
        "purpose_limited",
        "no_impersonation",
        "not_minor",
        "accepted_terms",
    ]

    def all_granted(self) -> bool:
        return all(getattr(self, f) for f in self.REQUIRED)


class AuditLog(Base):
    """동의·차단·삭제·합성 이벤트 감사 기록."""
    __tablename__ = "audit_logs"
    id = Column(String, primary_key=True, default=_uuid)
    event = Column(String, nullable=False)   # consent_granted, blocked, deleted, synthesized ...
    user_id = Column(String, nullable=True)
    voice_id = Column(String, nullable=True)
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_now)


class Message(Base):
    __tablename__ = "messages"
    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    voice_id = Column(String, nullable=True)
    role = Column(String)        # user | assistant
    text = Column(Text)
    audio_path = Column(String, nullable=True)
    feedback = Column(Text, nullable=True)   # 발음/문법 교정
    created_at = Column(DateTime, default=_now)
