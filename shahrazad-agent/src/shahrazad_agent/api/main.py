"""FastAPI application — token minting and health."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from shahrazad_agent.api.routes import errors, health, sessions, token, topics, tts
from shahrazad_agent.config import bootstrap_env

bootstrap_env()

app = FastAPI(title="Shahrazad", description="MSA voice tutor API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(token.router)
app.include_router(topics.router)
app.include_router(sessions.router)
app.include_router(errors.router)
app.include_router(tts.router)


def run() -> None:
    import uvicorn

    uvicorn.run("shahrazad_agent.api.main:app", host="0.0.0.0", port=8000, reload=True)
