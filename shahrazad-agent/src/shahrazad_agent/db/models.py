"""SQLAlchemy models — shaped for Phase 2+ review and drills."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    room_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    topic_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    lesson_context: Mapped["LessonContext | None"] = relationship(back_populates="session")
    turns: Mapped[list["Turn"]] = relationship(back_populates="session")
    errors: Mapped[list["ErrorEntry"]] = relationship(back_populates="session")


class LessonContext(Base):
    __tablename__ = "lesson_contexts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), unique=True)
    context_type: Mapped[str] = mapped_column(String(32), nullable=False)
    context_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    session: Mapped[Session] = relationship(back_populates="lesson_context")


class Turn(Base):
    __tablename__ = "turns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), index=True)
    speaker: Mapped[str] = mapped_column(String(16), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    audio_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    session: Mapped[Session] = relationship(back_populates="turns")
    errors: Mapped[list["ErrorEntry"]] = relationship(back_populates="turn")


class ErrorEntry(Base):
    __tablename__ = "error_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), index=True)
    turn_id: Mapped[str] = mapped_column(ForeignKey("turns.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    learner_text: Mapped[str] = mapped_column(Text, nullable=False)
    learner_audio_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    correct_form: Mapped[str] = mapped_column(Text, nullable=False)
    explanation_ar: Mapped[str] = mapped_column(Text, nullable=False)
    explanation_en: Mapped[str] = mapped_column(Text, nullable=False)
    detector: Mapped[str] = mapped_column(String(32), nullable=False)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    session: Mapped[Session] = relationship(back_populates="errors")
    turn: Mapped[Turn] = relationship(back_populates="errors")
    drill_attempts: Mapped[list["DrillAttempt"]] = relationship(back_populates="error_entry")


class DrillAttempt(Base):
    __tablename__ = "drill_attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), index=True)
    error_entry_id: Mapped[str | None] = mapped_column(ForeignKey("error_entries.id"), nullable=True)
    target_text: Mapped[str] = mapped_column(Text, nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    accuracy_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    completeness_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    fluency_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    scoring_mode: Mapped[str] = mapped_column(String(16), default="text_match")
    passed: Mapped[bool] = mapped_column(default=False)
    learner_audio_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    error_entry: Mapped[ErrorEntry | None] = relationship(back_populates="drill_attempts")
