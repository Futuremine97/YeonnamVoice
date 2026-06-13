#!/usr/bin/env python3
"""English For Us — 무설치(zero-dependency) 프로토타입 서버.

표준 라이브러리만 사용한다. 설치 없이 다음 한 줄로 실행:

    python3 server.py

(포트 8000). FastAPI 버전(app/)과 동일한 API·로직을 제공하되, pip 설치가
어려운 환경을 위해 stdlib만으로 구현했다. TTS는 실제 들리는 짧은 사인파
WAV를 생성한다(목소리 복제 자리표시자). 저장은 메모리 기반.
"""
import json
import hashlib
import math
import re
import struct
import time
import uuid
import wave
import io
import os
import threading
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

CONSENT_VERSION = "2026-06-13"
MAX_SYNTH_PER_HOUR = 60
AUDIO_DIR = os.path.join(os.path.dirname(__file__), "data", "generated")
os.makedirs(AUDIO_DIR, exist_ok=True)
FRONTEND_FILE = os.path.join(os.path.dirname(__file__), "..", "frontend", "index.html")

# 답변 엔진 설정 (런타임 토글). 키/제공자는 환경변수 또는 /settings로 주입.
#   provider: mock | anthropic | openai | openai_compat(로컬 Ollama·LM Studio 등)
SETTINGS = {
    "use_ai": os.environ.get("EFU_USE_AI", "") == "1",
    "provider": os.environ.get("EFU_AI_PROVIDER", "anthropic"),
    "model": os.environ.get("EFU_MODEL", "claude-sonnet-4-6"),
    "api_key": (os.environ.get("EFU_AI_API_KEY")
                or os.environ.get("EFU_ANTHROPIC_API_KEY")
                or os.environ.get("EFU_OPENAI_API_KEY") or ""),
    "base_url": os.environ.get("EFU_AI_BASE_URL", ""),  # openai_compat/로컬용
    # 블록체인(코인 발행) 설정 — 공개값만, 비밀키는 절대 저장하지 않음(서명은 사용자 지갑)
    "chain_id": os.environ.get("EFU_CHAIN_ID", ""),
    "chain_name": os.environ.get("EFU_CHAIN_NAME", "Sepolia testnet"),
    "registry_address": os.environ.get("EFU_REGISTRY_ADDRESS", ""),
    "license_address": os.environ.get("EFU_LICENSE_ADDRESS", ""),
    "coin_address": os.environ.get("EFU_COIN_ADDRESS", ""),
    "explorer_base": os.environ.get("EFU_EXPLORER_BASE", "https://sepolia.etherscan.io"),
}

_ADDR_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
_HEX32_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")


def _settings_view():
    return {"use_ai": SETTINGS["use_ai"], "provider": SETTINGS["provider"],
            "model": SETTINGS["model"], "base_url": SETTINGS["base_url"],
            "has_key": bool(SETTINGS["api_key"]),
            "chain_id": SETTINGS["chain_id"], "chain_name": SETTINGS["chain_name"],
            "registry_address": SETTINGS["registry_address"],
            "license_address": SETTINGS["license_address"],
            "coin_address": SETTINGS["coin_address"],
            "explorer_base": SETTINGS["explorer_base"]}


def consent_hash(vid, consent, version):
    """동의 기록의 정규화 sha256 → 0x...(bytes32). 온체인 프로비넌스에 사용."""
    payload = json.dumps({"voice_id": vid, "consent": consent, "version": version},
                         sort_keys=True, ensure_ascii=False)
    return "0x" + hashlib.sha256(payload.encode("utf-8")).hexdigest()

# ----------------- 메모리 저장소 -----------------
LOCK = threading.Lock()
DB = {
    "users": {},        # id -> user
    "voices": {},       # id -> voice
    "consents": {},     # voice_id -> consent
    "orders": {},       # id -> order
    "entitlements": [],  # list of {user_id, voice_id, order_id, active}
    "audit": [],        # list of events
    "synth_log": {},    # voice_id -> [timestamps]
}


def uid():
    return uuid.uuid4().hex


def log(event, **kw):
    DB["audit"].append({"event": event, "at": time.time(), **kw})


# ----------------- 모더레이션 -----------------
PATTERNS = {
    "impersonation": [r"pretend (to be|you are)\s+\w+",
                      r"act as (the )?(president|ceo|celebrity|\w+ trump|\w+ musk)",
                      r"(흉내|사칭|인 척).{0,10}(말해|해줘)", r"なりきっ|のふりをして"],
    "hate_harassment": [r"\b(kill|hurt|threaten)\s+(you|him|her|them)\b"],
    "minor_sexual": [r"\b(child|minor|underage)\b.{0,20}\b(sex|nude|naked)\b"],
    "fraud": [r"\b(phishing|scam script|wire transfer|bank password|otp code)\b",
              r"(피싱|보이스피싱|송금).{0,10}(대본|스크립트)"],
}
SELF_HARM = [r"\b(kill myself|suicide|end my life|self[- ]harm)\b", r"(자살|죽고 싶|자해)"]
SELF_HARM_MSG = ("힘든 마음이 느껴집니다. 이 주제는 민감해서 음성 합성으로는 다루지 않습니다. "
                 "지금 많이 괴롭다면 혼자 견디지 말고 가까운 사람이나 전문가의 도움을 받아보세요.")
BLOCK_MSGS = {
    "impersonation": "특정 인물 사칭·흉내 요청은 처리할 수 없습니다. 사칭은 약관에서 금지됩니다.",
    "hate_harassment": "혐오·위협·괴롭힘에 해당하는 요청은 처리할 수 없습니다.",
    "minor_sexual": "미성년자 관련 부적절한 요청은 처리할 수 없습니다.",
    "fraud": "사기·피싱 등 불법 목적의 요청은 처리할 수 없습니다.",
}


def moderate(text):
    low = text.lower()
    for p in SELF_HARM:
        if re.search(p, low) or re.search(p, text):
            return False, "self_harm", SELF_HARM_MSG
    for cat, pats in PATTERNS.items():
        for p in pats:
            if re.search(p, low) or re.search(p, text):
                return False, cat, BLOCK_MSGS[cat]
    return True, None, None


def rate_ok(voice_id):
    now = time.time()
    hist = [t for t in DB["synth_log"].get(voice_id, []) if now - t < 3600]
    if len(hist) >= MAX_SYNTH_PER_HOUR:
        DB["synth_log"][voice_id] = hist
        return False
    hist.append(now)
    DB["synth_log"][voice_id] = hist
    return True


# ----------------- mock TTS (실제 들리는 WAV) -----------------
def synth_wav(text, voice_id):
    """짧은 사인파 비프 WAV 생성 + 워터마크 메타데이터. (실엔진 자리표시자)"""
    name = f"{voice_id}_{uid()[:8]}.wav"
    path = os.path.join(AUDIO_DIR, name)
    rate, dur = 16000, 0.6
    freq = 330 + (sum(map(ord, text[:8])) % 220)  # 텍스트마다 살짝 다른 음
    with wave.open(path, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = b"".join(
            struct.pack("<h", int(12000 * math.sin(2 * math.pi * freq * (i / rate))))
            for i in range(int(rate * dur))
        )
        w.writeframes(frames)
    with open(path + ".meta.json", "w", encoding="utf-8") as f:
        json.dump({"synthetic": True, "service": "english_for_us",
                   "voice_id": voice_id, "generated_at": time.time(),
                   "text_preview": text[:80]}, f, ensure_ascii=False)
    return name


# ----------------- mock STT (학습자 음성 인식) -----------------
# 실서비스: OpenAI Whisper API. 프로토타입은 녹음 길이에 따라 샘플 문장을 고른다.
_STT_SAMPLES = [
    "Hi! How are you doing today?",
    "I want to talk about my weekend.",
    "Can you help me practice English?",
    "I had a really busy day at work.",
    "Let's talk about travel and food.",
    "What do you usually do on weekends?",
]


def transcribe_audio(audio_b64: str) -> str:
    if not audio_b64:
        return "(음성이 비어 있습니다)"
    # 실엔진 슬롯:
    #   from openai import OpenAI
    #   text = OpenAI().audio.transcriptions.create(model="whisper-1", file=...).text
    idx = len(audio_b64) % len(_STT_SAMPLES)
    return _STT_SAMPLES[idx]


# ----------------- mock LLM (자유 회화) -----------------
# 주제별 후속 질문 (키워드 매칭). 실엔진 연동 전까지 대화를 살아있게 한다.
TOPIC_FOLLOWUPS = {
    ("work", "job", "office", "boss", "회사", "일"): [
        "What do you do for work?", "Do you enjoy your job?",
        "What's the most challenging part of your work?"],
    ("food", "eat", "lunch", "dinner", "restaurant", "음식", "밥"): [
        "What's your favorite food?", "Did you cook it yourself or eat out?",
        "Do you like trying food from other countries?"],
    ("travel", "trip", "vacation", "여행"): [
        "Where did you go?", "What was the best part of the trip?",
        "Where would you like to travel next?"],
    ("movie", "music", "game", "hobby", "취미", "영화", "음악"): [
        "What kind of movies do you enjoy?", "Who's your favorite artist?",
        "How often do you do that?"],
    ("weekend", "yesterday", "today", "주말", "오늘", "어제"): [
        "What did you do?", "Sounds nice! Was it relaxing?",
        "Do you have any plans for tomorrow?"],
    ("study", "english", "learn", "school", "공부", "영어", "학교"): [
        "How long have you been studying English?",
        "What's the hardest part for you?", "What's your goal with English?"],
}
GENERIC_FOLLOWUPS = [
    "That's interesting! Can you tell me more?",
    "Nice! How did that make you feel?",
    "I see. What happened next?",
    "Great! Why do you think so?",
    "Cool! Could you give me an example?",
]
OPENERS = ["That's great!", "Oh, nice!", "Awesome!", "I love that.", "Good for you!", "Interesting!"]

# 흔한 한국어식 영어 실수 → 교정 (간단 휴리스틱)
CORRECTIONS = [
    (r"\bi am agree\b", "I agree", "'I am agree' 대신 'I agree'가 맞아요 (agree는 동사예요)."),
    (r"\bi have interest in\b", "I'm interested in", "더 자연스럽게는 \"I'm interested in ...\""),
    (r"\bvery much (good|nice|fun)\b", r"really \1", "'very much good'보다 'really good'이 자연스러워요."),
    (r"\bhow about you\?*$", "How about you?", "좋아요! 'How about you?'는 아주 자연스러운 표현이에요."),
    (r"\bi will go to home\b", "I'll go home", "'go to home'이 아니라 'go home'이에요 (home은 부사)."),
    (r"\bmany informations\b", "a lot of information", "'information'은 셀 수 없어서 's'를 안 붙여요."),
    (r"\bi didn't went\b", "I didn't go", "did 뒤에는 동사원형: 'didn't go'."),
]


def _correct(text, native):
    low = text.lower()
    for pat, fix, ko in CORRECTIONS:
        if re.search(pat, low):
            if native == "ja":
                return f"(添削) より自然な表現: \"{re.sub(pat, fix, low)}\""
            return f"(교정) {ko}"
    # 길이 기반 가벼운 격려
    if len(text.split()) < 3:
        if native == "ja":
            return "(ヒント) もう少し詳しく、文で話してみましょう。"
        return "(팁) 한 문장으로 조금 더 자세히 말해보면 좋아요. 예: \"I had a busy day because...\""
    if native == "ja":
        return "(添削) 自然な英語です。その調子！"
    return "(교정) 자연스러운 문장이에요. 아주 좋아요! 👍"


def _hash_pick(seq, seed_text):
    return seq[sum(map(ord, seed_text)) % len(seq)]


def llm_reply(text, native, level):
    low = text.lower()
    followup = None
    for keys, qs in TOPIC_FOLLOWUPS.items():
        if any(k in low for k in keys):
            followup = _hash_pick(qs, text)
            break
    if not followup:
        followup = _hash_pick(GENERIC_FOLLOWUPS, text)
    reply = f"{_hash_pick(OPENERS, text)} {followup}"
    return reply, _correct(text, native)


# ----------------- 실제 대화 AI (멀티 제공자) -----------------
def _tutor_system(native, level):
    lang = "Japanese" if native == "ja" else "Korean"
    return (
        f"You are a warm, encouraging English conversation tutor for a {level}-level "
        f"learner whose native language is {lang}.\n"
        "CONTEXT & CONTINUITY (very important): The messages include the full recent "
        "conversation. Read it carefully and stay coherent. Remember and reuse details the "
        "learner shared earlier (their name, job, interests, plans, problems). Refer back to "
        "what they just said, build on the current topic instead of switching randomly, and "
        "ask a relevant follow-up question that deepens THIS conversation. Avoid repeating a "
        "question you already asked.\n"
        "Keep the reply natural and short (1-3 sentences). Then give brief, friendly feedback "
        f"on grammar/word-choice/pronunciation from the learner's LAST message, written in {lang}. "
        "If the message was already good, say so briefly.\n"
        'Respond ONLY as compact JSON of the form '
        '{"reply":"<english reply>","feedback":"<feedback in learner language>"} '
        "with no markdown and no extra text."
    )


def _history_msgs(history, text):
    msgs = []
    for h in (history or [])[-20:]:
        role = "assistant" if h.get("role") == "assistant" else "user"
        c = (h.get("text") or "").strip()
        if c:
            msgs.append({"role": role, "content": c})
    msgs.append({"role": "user", "content": text})
    return msgs


def _parse_reply(out):
    out = (out or "").strip()
    try:
        s = out[out.find("{"): out.rfind("}") + 1]
        obj = json.loads(s)
        return obj.get("reply", out) or out, obj.get("feedback", "")
    except Exception:
        return out, ""


def _post_json(url, payload, headers, timeout=60):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def anthropic_reply(text, native, level, history):
    key = SETTINGS["api_key"]
    if not key:
        raise RuntimeError("Anthropic API 키가 없습니다.")
    payload = {"model": SETTINGS["model"], "max_tokens": 500,
               "system": _tutor_system(native, level),
               "messages": _history_msgs(history, text)}
    data = _post_json("https://api.anthropic.com/v1/messages", payload,
                      {"content-type": "application/json", "x-api-key": key,
                       "anthropic-version": "2023-06-01"})
    out = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    return _parse_reply(out)


def openai_compatible_reply(text, native, level, history):
    """OpenAI 및 OpenAI 호환(로컬 Ollama·LM Studio, OpenRouter 등) 공용.

    base_url 예: https://api.openai.com/v1  |  http://localhost:11434/v1 (Ollama)
    """
    base = (SETTINGS["base_url"] or "https://api.openai.com/v1").rstrip("/")
    headers = {"content-type": "application/json"}
    if SETTINGS["api_key"]:
        headers["Authorization"] = "Bearer " + SETTINGS["api_key"]
    messages = [{"role": "system", "content": _tutor_system(native, level)}] + \
        _history_msgs(history, text)
    payload = {"model": SETTINGS["model"], "messages": messages, "temperature": 0.7}
    data = _post_json(base + "/chat/completions", payload, headers)
    out = data["choices"][0]["message"]["content"]
    return _parse_reply(out)


_PROVIDERS = {
    "anthropic": anthropic_reply,
    "openai": openai_compatible_reply,
    "openai_compat": openai_compatible_reply,
}


def get_reply(text, native, level, history):
    """엔진 분기. AI ON이고 제공자 함수가 있으면 호출, 실패/OFF면 mock. (reply, feedback, engine)."""
    if SETTINGS["use_ai"]:
        fn = _PROVIDERS.get(SETTINGS["provider"])
        if fn:
            try:
                r, f = fn(text, native, level, history)
                if r:
                    return r, f, f"{SETTINGS['provider']}:{SETTINGS['model']}"
            except Exception as e:
                r, f = llm_reply(text, native, level)
                return r, f, f"mock (AI 호출 실패: {e})"
    r, f = llm_reply(text, native, level)
    return r, f, "mock"


# ----------------- 헬퍼 -----------------
def has_entitlement(user_id, voice_id):
    return any(e["user_id"] == user_id and e["voice_id"] == voice_id and e["active"]
               for e in DB["entitlements"])


def can_use(user_id, voice):
    return voice["owner_id"] == user_id or has_entitlement(user_id, voice["id"])


def catalog_item(v, user_id=None):
    owned = bool(user_id) and (v["owner_id"] == user_id or has_entitlement(user_id, v["id"]))
    return {"id": v["id"], "display_name": v["display_name"], "accent": v["accent"],
            "gender": v["gender"], "description": v["description"],
            "price_cents": v["price_cents"], "sample_seconds": v["sample_seconds"],
            "owned": owned}


# ----------------- HTTP 핸들러 -----------------
class H(BaseHTTPRequestHandler):
    def _send(self, code, obj=None, raw=None, ctype="application/json"):
        self.send_response(code)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        if raw is not None:
            self.send_header("Content-Type", ctype)
            self.end_headers()
            self.wfile.write(raw)
            return
        body = json.dumps(obj, ensure_ascii=False).encode() if obj is not None else b""
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _err(self, code, detail):
        self._send(code, {"detail": detail})

    def _body(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return {}

    def log_message(self, *a):
        pass  # 조용히

    def do_OPTIONS(self):
        self._send(204)

    def do_GET(self):
        u = urlparse(self.path)
        path, q = u.path, parse_qs(u.query)
        with LOCK:
            if path == "/":
                return self._send(200, {"service": "English For Us API (stdlib)",
                                        "status": "ok", "engines": {"tts": "mock-wav",
                                        "stt": "mock", "llm": "mock"}})
            if path == "/health":
                return self._send(200, {"ok": True})
            if path in ("/app", "/app/", "/index.html"):
                # 프런트엔드를 같은 origin으로 서빙 → 폰 WebView가 주소 하나로 전부 사용
                try:
                    with open(FRONTEND_FILE, "rb") as f:
                        return self._send(200, raw=f.read(), ctype="text/html; charset=utf-8")
                except Exception:
                    return self._err(404, "frontend not found")
            if path == "/settings":
                return self._send(200, _settings_view())
            m = re.match(r"^/users/([^/]+)$", path)
            if m:
                user = DB["users"].get(m.group(1))
                return self._send(200, user) if user else self._err(404, "user not found")
            m = re.match(r"^/voices/([^/]+)$", path)
            if m:
                v = DB["voices"].get(m.group(1))
                if not v or v["status"] == "DELETED":
                    return self._err(404, "voice not found")
                return self._send(200, v)
            if path == "/catalog/voices":
                uidq = (q.get("user_id") or [None])[0]
                accent = (q.get("accent") or [None])[0]
                items = [catalog_item(v, uidq) for v in DB["voices"].values()
                         if v["is_listed"] and v["status"] == "ACTIVE"
                         and (not accent or v["accent"] == accent)]
                return self._send(200, items)
            if path == "/catalog/my-voices":
                uidq = (q.get("user_id") or [None])[0]
                ids = {e["voice_id"] for e in DB["entitlements"]
                       if e["user_id"] == uidq and e["active"]}
                ids |= {v["id"] for v in DB["voices"].values()
                        if v["owner_id"] == uidq and v["status"] == "ACTIVE"}
                out = [catalog_item(DB["voices"][i], uidq) for i in ids
                       if i in DB["voices"] and DB["voices"][i]["status"] == "ACTIVE"]
                return self._send(200, out)
            m = re.match(r"^/chat/audio/(.+)$", path)
            if m:
                fp = os.path.join(AUDIO_DIR, os.path.basename(m.group(1)))
                if not os.path.exists(fp):
                    return self._err(404, "audio not found")
                with open(fp, "rb") as f:
                    return self._send(200, raw=f.read(), ctype="audio/wav")
        self._err(404, "not found")

    def do_DELETE(self):
        m = re.match(r"^/voices/([^/]+)$", urlparse(self.path).path)
        if not m:
            return self._err(404, "not found")
        with LOCK:
            v = DB["voices"].get(m.group(1))
            if not v or v["status"] == "DELETED":
                return self._err(404, "voice not found")
            v["status"] = "DELETED"
            v["source_b64"] = None
            v["embedding"] = None
            for fn in os.listdir(AUDIO_DIR):
                if fn.startswith(v["id"]):
                    try:
                        os.remove(os.path.join(AUDIO_DIR, fn))
                    except OSError:
                        pass  # 파일 제거 실패는 삭제 처리를 막지 않음

            log("voice_deleted", voice_id=v["id"], user_id=v["owner_id"])
            return self._send(200, {"deleted": True, "voice_id": v["id"]})

    def do_POST(self):
        u = urlparse(self.path)
        path, q = u.path, parse_qs(u.query)
        body = self._body()
        with LOCK:
            if path == "/settings":
                if "api_key" in body:
                    SETTINGS["api_key"] = (body.get("api_key") or "").strip()
                if "provider" in body and body.get("provider"):
                    SETTINGS["provider"] = body["provider"].strip()
                if "model" in body and body.get("model"):
                    SETTINGS["model"] = body["model"].strip()
                if "base_url" in body:
                    SETTINGS["base_url"] = (body.get("base_url") or "").strip()
                if "use_ai" in body:
                    SETTINGS["use_ai"] = bool(body["use_ai"])
                # 블록체인 설정 (공개값만). 컨트랙트 주소는 형식 검증.
                for k in ("registry_address", "license_address", "coin_address"):
                    if k in body:
                        v = (body.get(k) or "").strip()
                        if v and not _ADDR_RE.match(v):
                            return self._err(422, f"{k}: 잘못된 컨트랙트 주소 형식")
                        SETTINGS[k] = v
                if "chain_id" in body:
                    SETTINGS["chain_id"] = str(body.get("chain_id") or "").strip()
                if "chain_name" in body:
                    SETTINGS["chain_name"] = (body.get("chain_name") or "").strip()
                if "explorer_base" in body:
                    eb = (body.get("explorer_base") or "").strip()
                    if eb and not eb.startswith(("http://", "https://")):
                        return self._err(422, "explorer_base: http(s) URL 이어야 합니다")
                    SETTINGS["explorer_base"] = eb.rstrip("/")
                log("settings_update",
                    detail=f"use_ai={SETTINGS['use_ai']} provider={SETTINGS['provider']} chain={SETTINGS['chain_id']}")
                return self._send(200, _settings_view())

            m = re.match(r"^/voices/([^/]+)/onchain$", path)
            if m:
                v = DB["voices"].get(m.group(1))
                if not v or v["status"] == "DELETED":
                    return self._err(404, "voice not found")
                tx = (body.get("tx_hash") or "").strip()
                if not _HEX32_RE.match(tx):
                    return self._err(422, "tx_hash 형식 오류")
                wallet = (body.get("wallet") or "").strip()
                if wallet and not _ADDR_RE.match(wallet):
                    return self._err(422, "wallet 주소 형식 오류")
                token_id = body.get("token_id")
                try:
                    token_id = int(token_id) if token_id is not None else None
                except (TypeError, ValueError):
                    return self._err(422, "token_id 형식 오류")
                v["onchain"] = {"tx_hash": tx, "token_id": token_id,
                                "chain_id": str(body.get("chain_id") or ""),
                                "wallet": wallet, "at": time.time()}
                log("voice_minted", user_id=v["owner_id"], voice_id=v["id"], detail=tx)
                return self._send(200, {"ok": True, "onchain": v["onchain"]})

            if path == "/users":
                for usr in DB["users"].values():
                    if usr["email"] == body.get("email"):
                        return self._send(200, usr)
                user = {"id": uid(), "email": body.get("email", ""),
                        "native_language": body.get("native_language", "ko"),
                        "level": body.get("level", "intermediate")}
                DB["users"][user["id"]] = user
                return self._send(200, user)

            if path == "/voices":
                user = DB["users"].get(body.get("user_id"))
                if not user:
                    return self._err(404, "user not found")
                consent = body.get("consent") or {}
                req = ["owns_or_authorized", "purpose_limited", "no_impersonation",
                       "not_minor", "accepted_terms"]
                vid = uid()
                DB["consents"][vid] = {**{k: bool(consent.get(k)) for k in req},
                                       "consent_version": CONSENT_VERSION}
                if not all(consent.get(k) for k in req):
                    log("consent_rejected", voice_id=vid, user_id=user["id"])
                    return self._err(403, "필수 동의 항목에 모두 동의해야 음성을 등록할 수 있습니다.")
                audio_b64 = body.get("audio_b64") or ""
                chash = consent_hash(vid, {k: bool(consent.get(k)) for k in req}, CONSENT_VERSION)
                DB["consents"][vid]["consent_hash"] = chash
                voice = {"id": vid, "owner_id": user["id"],
                         "display_name": body.get("display_name", "voice"),
                         "status": "ACTIVE", "sample_seconds": max(1, len(audio_b64) // 20000),
                         "source_b64": audio_b64[:100], "embedding": {"note": "mock"},
                         "is_listed": False, "price_cents": 0, "accent": "American",
                         "gender": "unspecified", "description": None,
                         "consent_hash": chash, "onchain": None}
                DB["voices"][vid] = voice
                log("consent_granted", voice_id=vid, user_id=user["id"])
                log("voice_activated", voice_id=vid, user_id=user["id"])
                return self._send(200, voice)

            m = re.match(r"^/catalog/voices/([^/]+)/publish$", path)
            if m:
                v = DB["voices"].get(m.group(1))
                if not v or v["status"] != "ACTIVE":
                    return self._err(403, "ACTIVE(동의 완료) 상태의 음성만 판매 등록할 수 있습니다.")
                if int(body.get("price_cents", 0)) < 0:
                    return self._err(422, "가격은 0 이상이어야 합니다.")
                v["is_listed"] = True
                v["price_cents"] = int(body.get("price_cents", 0))
                v["accent"] = body.get("accent", "American")
                v["gender"] = body.get("gender", "unspecified")
                v["description"] = body.get("description")
                log("voice_listed", voice_id=v["id"], user_id=v["owner_id"])
                return self._send(200, catalog_item(v))

            m = re.match(r"^/catalog/voices/([^/]+)/purchase$", path)
            if m:
                v = DB["voices"].get(m.group(1))
                user = DB["users"].get(body.get("user_id"))
                if not user:
                    return self._err(404, "user not found")
                if not v or not v["is_listed"] or v["status"] != "ACTIVE":
                    return self._err(404, "구매 가능한 음성이 아닙니다.")
                if can_use(user["id"], v):
                    return self._err(409, "이미 보유한 음성입니다.")
                oid = uid()
                token = "tok_mock_" + uid()[:12]
                DB["orders"][oid] = {"id": oid, "user_id": user["id"], "voice_id": v["id"],
                                     "amount_cents": v["price_cents"], "currency": "usd",
                                     "status": "PENDING", "token": token}
                log("order_created", voice_id=v["id"], user_id=user["id"], detail=oid)
                return self._send(200, {"order_id": oid, "status": "PENDING",
                                        "amount_cents": v["price_cents"], "currency": "usd",
                                        "payment_token": token})

            m = re.match(r"^/catalog/orders/([^/]+)/confirm$", path)
            if m:
                order = DB["orders"].get(m.group(1))
                if not order:
                    return self._err(404, "order not found")
                token = (q.get("payment_token") or [body.get("payment_token")])[0]
                if order["status"] == "PAID":
                    return self._send(200, {"order_id": order["id"], "status": "PAID",
                                            "amount_cents": order["amount_cents"], "currency": "usd"})
                if not token or not token.startswith("tok_mock_"):
                    order["status"] = "FAILED"
                    return self._err(402, "결제 확정에 실패했습니다.")
                order["status"] = "PAID"
                DB["entitlements"].append({"user_id": order["user_id"],
                                           "voice_id": order["voice_id"],
                                           "order_id": order["id"], "active": True})
                log("entitlement_granted", voice_id=order["voice_id"], user_id=order["user_id"])
                return self._send(200, {"order_id": order["id"], "status": "PAID",
                                        "amount_cents": order["amount_cents"], "currency": "usd"})

            if path == "/chat":
                user = DB["users"].get(body.get("user_id"))
                if not user:
                    return self._err(404, "user not found")
                text = body.get("text", "")
                ok, cat, msg = moderate(text)
                if not ok:
                    log("blocked", user_id=user["id"], detail=cat)
                    return self._send(200, {"reply_text": "", "blocked": True,
                                            "block_reason": msg, "feedback": None})
                voice_id = body.get("voice_id")
                voice = None
                if voice_id:
                    voice = DB["voices"].get(voice_id)
                    if not voice or voice["status"] != "ACTIVE":
                        return self._err(403, "활성화(동의 완료)된 음성이 아닙니다.")
                    if not can_use(user["id"], voice):
                        return self._err(402, "이 목소리는 구매 후 사용할 수 있습니다. 스토어에서 구매해 주세요.")
                reply, fb, engine = get_reply(text, user["native_language"], user["level"], body.get("history"))
                audio_url = None
                if voice:
                    if not rate_ok(voice["id"]):
                        return self._err(429, "합성 한도를 초과했습니다. 잠시 후 다시 시도하세요.")
                    name = synth_wav(reply, voice["id"])
                    audio_url = f"/chat/audio/{name}"
                    log("synthesized", voice_id=voice["id"], user_id=user["id"])
                return self._send(200, {"reply_text": reply, "feedback": fb,
                                        "audio_url": audio_url, "blocked": False,
                                        "engine": engine})

            if path == "/chat/transcribe":
                # 학습자 음성(base64) → 텍스트. 실서비스는 Whisper API로 교체.
                audio_b64 = body.get("audio_b64") or ""
                text = transcribe_audio(audio_b64)
                return self._send(200, {"text": text})

        self._err(404, "not found")


def seed_demo():
    """데모용 원어민 튜터를 카탈로그에 미리 등록(메모리). 갤러리가 비지 않게."""
    sys_id = "system"
    DB["users"][sys_id] = {"id": sys_id, "email": "system@efu",
                           "native_language": "en", "level": "native"}
    demo = [
        ("Emma", "American", "female", 0, "밝고 또렷한 미국식 발음 · 일상 회화에 적합", 92),
        ("James", "British", "male", 0, "차분한 영국식 발음 · 비즈니스/격식 표현", 110),
        ("Olivia", "Australian", "female", 199, "친근한 호주식 발음 · 캐주얼 대화", 78),
        ("Noah", "American", "male", 0, "느긋한 미국식 발음 · 발음 따라하기 좋음", 65),
        ("Sophia", "British", "female", 299, "또박또박 영국식 발음 · 초급자 추천", 130),
    ]
    for i, (name, accent, gender, price, desc, secs) in enumerate(demo):
        vid = f"demo{i+1}"
        DB["voices"][vid] = {
            "id": vid, "owner_id": sys_id, "display_name": name, "status": "ACTIVE",
            "sample_seconds": secs, "source_b64": "", "embedding": {"note": "demo"},
            "is_listed": True, "price_cents": price, "accent": accent,
            "gender": gender, "description": desc,
        }
    log("seed_demo", detail=f"{len(demo)} tutors")


def main():
    port = int(os.environ.get("PORT", "8000"))
    seed_demo()
    srv = ThreadingHTTPServer(("0.0.0.0", port), H)
    print(f"English For Us (stdlib) → http://localhost:{port}  (Ctrl+C 로 종료)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n종료")


if __name__ == "__main__":
    main()
