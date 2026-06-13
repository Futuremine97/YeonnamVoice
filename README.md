# English For Us

원어민/영어사용자의 1~5분 음성으로 목소리를 복제하고, 그 목소리로 한국·일본 학습자가 영어 회화를 연습하는 웹·모바일 서비스. 목소리는 **마켓플레이스에서 선택·구매**해 사용한다.

## 문서

| 파일 | 내용 |
|------|------|
| `기술설계문서.md` | 전체 아키텍처·모델 선정·비용·로드맵 |
| `동의_악용방지_기능설계.md` | 동의 게이트·모더레이션·워터마크·삭제권 |
| `마켓플레이스_설계.md` | 목소리 프로필·구매 플로우·정산·라이선스 |
| `모바일앱_설계.md` | React Native 앱 설계 |

## 프로토타입 실행

### ✅ 가장 간단한 방법 — 무설치 서버 (설치 0개)

`pip`가 없거나 설치가 막힌 환경에서도 **`python3` 하나로** 바로 돈다.

터미널 ① (백엔드):
```bash
cd ~/Documents/english_forus/backend
python3 server.py
# → http://localhost:8000
```

터미널 ② (프론트엔드, 새 탭 ⌘T):
```bash
cd ~/Documents/english_forus/frontend
python3 -m http.server 5173
# 브라우저: http://localhost:5173
```

> 두 개를 **각각 다른 터미널 탭**에서 실행해야 한다(백엔드는 계속 떠 있어야 함).
> 이 무설치 서버는 표준 라이브러리만 쓰며, 실제 들리는 WAV 오디오를 생성한다.

### (선택) FastAPI 버전 — 실제 엔진 연동용

```bash
cd backend
python3 -m pip install -r requirements.txt   # macOS: pip3 또는 python3 -m pip
python3 -m uvicorn app.main:app --reload --port 8000
# API 문서: http://localhost:8000/docs
```

TTS/STT/LLM은 기본 **mock**으로 동작한다(키 없이 실행됨). 실제 엔진은 환경변수로 교체:

```bash
export EFU_TTS_ENGINE=chatterbox      # Chatterbox 설치 후
export EFU_STT_ENGINE=whisper
export EFU_OPENAI_API_KEY=sk-...
export EFU_LLM_ENGINE=claude
export EFU_ANTHROPIC_API_KEY=sk-ant-...
```

### 2) 프론트엔드 (빌드 불필요)

```bash
cd frontend
python3 -m http.server 5173
# 브라우저에서 http://localhost:5173 접속
```

> 프론트는 CDN React 단일 파일이라 빌드가 필요 없다. 백엔드가 8000 포트에서 떠 있어야 한다.
> API 주소 변경: 브라우저 콘솔에서 `localStorage.setItem("efu_api","http://...")`.

## 핵심 흐름

1. **프로필 생성** → 모국어·레벨 설정
2. **목소리 등록** → 음성 업로드 + 5개 동의 항목 통과 → ACTIVE → (선택) 스토어 판매 공개
3. **스토어** → 원어민 목소리 탐색 → 구매(mock 결제) → 보유권 획득
4. **대화** → 보유한 목소리 선택 → 영어 대화 + 발음/문법 교정 + 복제 목소리 음성 재생

## 악용방지 (구현됨)

- 동의 미통과 음성은 비활성 → 대화 불가
- 미보유 목소리로 대화 시도 시 402(구매 필요)
- 입력 모더레이션: 사칭·혐오·미성년·사기·자해 차단
- 합성물 워터마크 메타데이터, voice별 레이트리밋, 감사 로그, 완전 삭제 API

## 상태

- 백엔드 로직(동의·모더레이션·레이트리밋·구매/보유권) 단위 검증 완료.
- TTS/STT/LLM/결제는 추상화된 mock — 실엔진/Stripe만 꽂으면 동작.

## 라이선스

[Apache License 2.0](LICENSE) — 상업적 이용·수정·배포 가능하며 특허 사용 허락을 포함합니다.
재배포 시 `LICENSE`와 `NOTICE`를 포함하세요. © 2026 Yeonnam Voice (English For Us).
