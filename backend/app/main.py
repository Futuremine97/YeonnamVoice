"""English For Us — FastAPI 진입점."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import init_db
from .routers import users, voices, chat, catalog

app = FastAPI(title=settings.app_name, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 프로토타입용. 운영 시 도메인 제한.
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users.router)
app.include_router(voices.router)
app.include_router(catalog.router)
app.include_router(chat.router)


@app.on_event("startup")
def _startup():
    init_db()


@app.get("/")
def root():
    return {
        "service": settings.app_name,
        "status": "ok",
        "engines": {
            "tts": settings.tts_engine,
            "stt": settings.stt_engine,
            "llm": settings.llm_engine,
        },
        "docs": "/docs",
    }


@app.get("/health")
def health():
    return {"ok": True}
