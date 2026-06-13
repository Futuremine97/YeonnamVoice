# English For Us — Android 앱 (WebView)

연결된 안드로이드 폰에서 영어 회화 학습 앱을 실행합니다. 앱은 같은 Wi‑Fi의 **PC에서 도는 서버**(server.py)의 화면을 불러옵니다.

> 🔒 **개인정보**: 이 앱은 폰의 사진·연락처·파일 등 어떤 데이터에도 접근하지 않습니다. 사용하는 권한은 **인터넷**과 **마이크(영어 발화 입력)** 뿐입니다.

## 동작 구조

```
[안드로이드 폰 앱(WebView)] ──같은 Wi-Fi──► [PC: python3 server.py :8000]
   /app 화면 로드 · 마이크로 영어 말하기 · 튜터 음성 듣기
```

백엔드가 화면(`/app`)과 API를 같은 주소로 제공하므로, 폰에서는 **PC 주소 한 번만** 입력하면 모든 기능이 동작합니다.

## 준비

1. **PC에서 서버 실행** (폰과 같은 Wi‑Fi):
   ```bash
   cd ~/Documents/english_forus/backend
   python3 server.py            # 0.0.0.0:8000 로 열림 (LAN 접속 가능)
   ```
2. **PC의 IP 주소 확인**:
   - macOS: `ipconfig getifaddr en0` (예: `192.168.0.10`)
   - 방화벽이 8000 포트 incoming을 막지 않는지 확인(맥: 시스템 설정 → 네트워크 → 방화벽).

## 빌드 & 설치 (Android Studio 권장)

1. Android Studio에서 **`android-app/` 폴더를 Open**.
2. Gradle 동기화가 끝나면(자동으로 Gradle/SDK 내려받음), 폰을 USB로 연결하고 **개발자 옵션 → USB 디버깅**을 켭니다.
3. 상단 기기 목록에서 본인 폰 선택 → **Run ▶**. 앱이 폰에 설치·실행됩니다.

### 명령줄로 설치(선택)
Android SDK가 설치돼 있으면:
```bash
cd android-app
./gradlew assembleDebug                      # APK 생성 (최초엔 gradlew를 Android Studio가 생성)
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

## 처음 실행

1. 앱을 처음 켜면 **PC 서버 주소 입력** 창이 뜹니다 → `http://<PC-IP>:8000` 입력 (예: `http://192.168.0.10:8000`).
2. 마이크 권한을 허용합니다.
3. 튜터를 고르고 대화를 시작하세요. 🎙로 영어를 말하면 인식되고, 튜터가 음성으로 답합니다.

> 주소를 잘못 입력했거나 서버가 꺼져 있으면 "서버에 연결할 수 없어요" 창이 다시 떠서 주소를 고칠 수 있습니다.

## 참고 / 한계

- **음성 인식(STT)**: 안드로이드 WebView는 브라우저 음성인식(Web Speech API)을 지원하지 않아, 폰에서는 서버 STT(현재 mock, Whisper 키 연결 시 실제 인식)로 자동 폴백됩니다. 실제 받아쓰기를 원하면 백엔드에 Whisper를 연결하세요.
- **튜터 음성 출력(TTS)**: 안드로이드 내장 음성합성으로 재생됩니다.
- **운영 배포**: 현재는 개발용으로 http(cleartext)를 허용합니다. 스토어 출시 시 서버를 https로 올리고 `network_security_config.xml`의 cleartext 허용을 제거하세요. 또한 결제/구매는 스토어 정책상 인앱결제(IAP)로 바꿔야 합니다(모바일앱_설계.md 참고).
- 이 앱은 `android-app/` 폴더에만 생성되며, 폰의 기존 데이터/폴더와 무관합니다.
