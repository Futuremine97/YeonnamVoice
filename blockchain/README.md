# VoiceCoin — 음성 저작권 토큰/NFT (테스트넷 프로토타입)

> ⚠️ **법적 고지**: 이 코드는 교육·프로토타입 목적의 **테스트넷용**입니다. 보안 감사를 받지 않았고, 투자 권유가 아닙니다. 실제 토큰 발행·판매는 한국을 포함한 각국에서 **가상자산·증권성·AML/KYC 규제** 대상일 수 있습니다. 메인넷 배포 전 반드시 변호사·보안감사·세무 검토를 받으세요. 실자금이 든 지갑 키를 사용하지 마세요.

## 컨트랙트 구성

| 컨트랙트 | 역할 |
|----------|------|
| `VoiceCoin.sol` (ERC-20, VOICE) | 라이선스·로열티·스테이킹 결제 토큰. 상한 + 민터 권한 |
| `VoiceRegistry.sol` (ERC-721) | 목소리=NFT. **동의 해시(프로비넌스)** + 억양·가격·로열티 기록. 동의 해시 없으면 등록 불가 |
| `VoiceLicense.sol` | 라이선스 결제 + **세션 사용량 로열티 분배**(소유자 pull 인출, 플랫폼 수수료) |
| `VoiceStaking.sol` | 스테이킹 + **스테이크 가중 거버넌스 투표**(시그널링) |

## 4가지 용도 매핑

- **라이선스 결제**: `VoiceLicense.buyLicense(voiceId)` — VOICE로 결제
- **사용량 기반 로열티**: `VoiceLicense.paySession(voiceId)` — 대화 세션마다 소액 결제→소유자 분배
- **소유권·동의 프로비넌스**: `VoiceRegistry` NFT + `consentHash`(off-chain 동의서의 해시)
- **스테이킹·거버넌스**: `VoiceStaking.stake / createProposal / vote`

## 실행 방법

```bash
cd blockchain
npm install                 # hardhat, OpenZeppelin 등 설치
npx hardhat compile         # 컴파일
npx hardhat test            # 단위 테스트 (핵심 시나리오)
```

로컬 체인 배포:
```bash
npx hardhat node            # 별도 터미널
npx hardhat run scripts/deploy.js --network localhost
```

테스트넷(Sepolia) 배포:
```bash
cp .env.example .env        # RPC URL/테스트 지갑 키 입력
npx hardhat run scripts/deploy.js --network sepolia
```

## 앱(English For Us)과의 연동 설계

오프체인 앱의 마켓플레이스가 온체인과 1:1로 대응됩니다.

| 앱(off-chain) | 온체인 |
|----------------|--------|
| 음성 등록 + 5개 동의 | `registerVoice(consentHash, ...)` — 동의서 해시를 박아 위변조 방지 |
| 목소리 구매(Entitlement) | `buyLicense(voiceId)` |
| 대화 1회 사용 | `paySession(voiceId)` → 사용량 로열티 |
| 제공자 정산(Payout) | `withdrawRoyalties()` |

백엔드는 동의 기록의 sha256을 `consentHash`로 전달하고, 결제/정산만 온체인에 위임하는 하이브리드 구조를 권장합니다(전 사용자 가스비 부담을 줄이기 위해 L2 또는 메타트랜잭션 고려).

## 토크노믹스/규제 상세

`../음성코인_설계.md` 참고.
