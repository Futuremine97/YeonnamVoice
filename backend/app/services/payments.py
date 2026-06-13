"""결제 추상화.

프로토타입은 MockPayments(즉시 성공 토큰 발급/확정). 실서비스는 Stripe 등으로 교체.
- create_intent: 결제 인텐트 생성 → 클라이언트 토큰 반환
- confirm: 토큰 확정 → 성공 여부
"""
import uuid
from abc import ABC, abstractmethod


class PaymentProvider(ABC):
    name = "abstract"

    @abstractmethod
    def create_intent(self, amount_cents: int, currency: str, order_id: str) -> tuple[str, str]:
        """반환: (provider_ref, client_token)"""
        ...

    @abstractmethod
    def confirm(self, provider_ref: str, token: str) -> bool:
        ...


class MockPayments(PaymentProvider):
    name = "mock"

    def create_intent(self, amount_cents: int, currency: str, order_id: str):
        ref = "pi_mock_" + uuid.uuid4().hex[:12]
        token = "tok_mock_" + uuid.uuid4().hex[:12]
        # 데모: ref↔token 매핑을 토큰 안에 인코딩(검증용)
        self._last = {ref: token}
        return ref, token

    def confirm(self, provider_ref: str, token: str) -> bool:
        # mock: 형식만 맞으면 성공 (무료(0원) 항목도 통과)
        return token.startswith("tok_mock_") and provider_ref.startswith("pi_mock_")


# 싱글턴
_provider = MockPayments()


def get_payments() -> PaymentProvider:
    return _provider
