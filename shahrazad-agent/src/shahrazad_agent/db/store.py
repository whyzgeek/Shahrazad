"""Async-safe persistence helpers (SQLAlchemy sync under asyncio.to_thread)."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from shahrazad_agent.db.models import DrillAttempt, ErrorEntry, LessonContext, Session, Turn


@dataclass
class ErrorRow:
    id: str
    session_id: str
    turn_id: str
    kind: str
    severity: str
    learner_text: str
    learner_audio_path: str | None
    correct_form: str
    explanation_ar: str
    explanation_en: str
    detector: str
    score: float | None
    turn_index: int
    created_at: datetime


class SessionStore:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    async def create_session(
        self,
        *,
        topic_id: str,
        room_name: str | None,
        context_type: str,
        context_payload: dict[str, Any],
        session_id: str | None = None,
    ) -> str:
        sid = session_id or str(uuid.uuid4())

        def _write() -> str:
            with self._session_factory() as db:
                db.add(
                    Session(
                        id=sid,
                        room_name=room_name,
                        topic_id=topic_id,
                    )
                )
                db.add(
                    LessonContext(
                        id=str(uuid.uuid4()),
                        session_id=sid,
                        context_type=context_type,
                        context_payload=context_payload,
                    )
                )
                db.commit()
            return sid

        return await asyncio.to_thread(_write)

    async def add_turn(
        self,
        *,
        session_id: str,
        speaker: str,
        text: str,
        turn_index: int,
        audio_path: str | None = None,
        turn_id: str | None = None,
    ) -> str:
        tid = turn_id or str(uuid.uuid4())

        def _write() -> str:
            with self._session_factory() as db:
                db.add(
                    Turn(
                        id=tid,
                        session_id=session_id,
                        speaker=speaker,
                        text=text,
                        audio_path=audio_path,
                        turn_index=turn_index,
                    )
                )
                db.commit()
            return tid

        return await asyncio.to_thread(_write)

    async def update_turn_audio(self, turn_id: str, audio_path: str) -> None:
        def _write() -> None:
            with self._session_factory() as db:
                turn = db.get(Turn, turn_id)
                if turn is not None:
                    turn.audio_path = audio_path
                    db.commit()

        await asyncio.to_thread(_write)

    async def get_latest_tutor_text(self, session_id: str) -> str | None:
        """Most recent tutor turn text (for judge context, e.g. name questions)."""

        def _read() -> str | None:
            with self._session_factory() as db:
                stmt = (
                    select(Turn.text)
                    .where(Turn.session_id == session_id, Turn.speaker == "tutor")
                    .order_by(Turn.turn_index.desc())
                    .limit(1)
                )
                return db.execute(stmt).scalar_one_or_none()

        return await asyncio.to_thread(_read)

    async def add_errors(self, rows: list[dict[str, Any]]) -> list[str]:
        if not rows:
            return []

        def _write() -> list[str]:
            ids: list[str] = []
            with self._session_factory() as db:
                for row in rows:
                    eid = row.get("id") or str(uuid.uuid4())
                    db.add(
                        ErrorEntry(
                            id=eid,
                            session_id=row["session_id"],
                            turn_id=row["turn_id"],
                            kind=row["kind"],
                            severity=row["severity"],
                            learner_text=row["learner_text"],
                            learner_audio_path=row.get("learner_audio_path"),
                            correct_form=row["correct_form"],
                            explanation_ar=row["explanation_ar"],
                            explanation_en=row["explanation_en"],
                            detector=row["detector"],
                            score=row.get("score"),
                        )
                    )
                    ids.append(eid)
                db.commit()
            return ids

        return await asyncio.to_thread(_write)

    async def count_errors(self, session_id: str) -> int:
        def _read() -> int:
            with self._session_factory() as db:
                return int(
                    db.scalar(
                        select(func.count())
                        .select_from(ErrorEntry)
                        .where(ErrorEntry.session_id == session_id)
                    )
                    or 0
                )

        return await asyncio.to_thread(_read)

    async def get_errors_for_prompt(
        self, session_id: str, *, max_turn_index: int
    ) -> list[ErrorRow]:
        if max_turn_index < 0:
            return []

        def _read() -> list[ErrorRow]:
            with self._session_factory() as db:
                stmt = (
                    select(ErrorEntry, Turn.turn_index)
                    .join(Turn, ErrorEntry.turn_id == Turn.id)
                    .where(
                        ErrorEntry.session_id == session_id,
                        Turn.turn_index <= max_turn_index,
                        ErrorEntry.resolved_at.is_(None),
                    )
                    .order_by(Turn.turn_index.desc(), ErrorEntry.created_at.desc())
                    .limit(8)
                )
                rows = db.execute(stmt).all()
                return [
                    ErrorRow(
                        id=err.id,
                        session_id=err.session_id,
                        turn_id=err.turn_id,
                        kind=err.kind,
                        severity=err.severity,
                        learner_text=err.learner_text,
                        learner_audio_path=err.learner_audio_path,
                        correct_form=err.correct_form,
                        explanation_ar=err.explanation_ar,
                        explanation_en=err.explanation_en,
                        detector=err.detector,
                        score=err.score,
                        turn_index=turn_index,
                        created_at=err.created_at,
                    )
                    for err, turn_index in rows
                ]

        return await asyncio.to_thread(_read)

    async def list_errors(self, session_id: str) -> list[dict[str, Any]]:
        def _read() -> list[dict[str, Any]]:
            with self._session_factory() as db:
                stmt = (
                    select(ErrorEntry, Turn.turn_index)
                    .join(Turn, ErrorEntry.turn_id == Turn.id)
                    .where(ErrorEntry.session_id == session_id)
                    .order_by(Turn.turn_index, ErrorEntry.created_at)
                )
                out: list[dict[str, Any]] = []
                for err, turn_index in db.execute(stmt).all():
                    out.append(
                        {
                            "id": err.id,
                            "turn_id": err.turn_id,
                            "turn_index": turn_index,
                            "kind": err.kind,
                            "severity": err.severity,
                            "learner_text": err.learner_text,
                            "learner_audio_path": err.learner_audio_path,
                            "correct_form": err.correct_form,
                            "explanation_ar": err.explanation_ar,
                            "explanation_en": err.explanation_en,
                            "detector": err.detector,
                            "score": err.score,
                            "acknowledged_at": err.acknowledged_at.isoformat()
                            if err.acknowledged_at
                            else None,
                            "resolved_at": err.resolved_at.isoformat()
                            if err.resolved_at
                            else None,
                            "created_at": err.created_at.isoformat(),
                        }
                    )
                return out

        return await asyncio.to_thread(_read)

    async def get_session_by_room(self, room_name: str) -> dict[str, Any] | None:
        def _read() -> dict[str, Any] | None:
            with self._session_factory() as db:
                session = db.scalar(select(Session).where(Session.room_name == room_name))
                if session is None:
                    return None
                return {
                    "id": session.id,
                    "room_name": session.room_name,
                    "topic_id": session.topic_id,
                }

        return await asyncio.to_thread(_read)

    async def resolve_error(self, error_id: str) -> bool:
        def _write() -> bool:
            with self._session_factory() as db:
                err = db.get(ErrorEntry, error_id)
                if err is None:
                    return False
                if err.resolved_at is None:
                    err.resolved_at = datetime.now(timezone.utc)
                    db.commit()
                return True

        return await asyncio.to_thread(_write)

    async def get_error(self, error_id: str) -> dict[str, Any] | None:
        def _read() -> dict[str, Any] | None:
            with self._session_factory() as db:
                err = db.get(ErrorEntry, error_id)
                if err is None:
                    return None
                return {
                    "id": err.id,
                    "session_id": err.session_id,
                    "turn_id": err.turn_id,
                    "kind": err.kind,
                    "learner_text": err.learner_text,
                    "correct_form": err.correct_form,
                    "explanation_ar": err.explanation_ar,
                    "explanation_en": err.explanation_en,
                    "resolved_at": err.resolved_at.isoformat() if err.resolved_at else None,
                }

        return await asyncio.to_thread(_read)

    async def add_drill_attempt(
        self,
        *,
        session_id: str,
        error_entry_id: str | None,
        target_text: str,
        attempt_number: int,
        accuracy_score: float | None,
        completeness_score: float | None,
        fluency_score: float | None,
        scoring_mode: str,
        passed: bool,
        learner_audio_path: str | None,
    ) -> str:
        attempt_id = str(uuid.uuid4())

        def _write() -> str:
            with self._session_factory() as db:
                db.add(
                    DrillAttempt(
                        id=attempt_id,
                        session_id=session_id,
                        error_entry_id=error_entry_id,
                        target_text=target_text,
                        attempt_number=attempt_number,
                        accuracy_score=accuracy_score,
                        completeness_score=completeness_score,
                        fluency_score=fluency_score,
                        scoring_mode=scoring_mode,
                        passed=passed,
                        learner_audio_path=learner_audio_path,
                    )
                )
                db.commit()
            return attempt_id

        return await asyncio.to_thread(_write)

    async def list_drills(self, session_id: str) -> list[dict[str, Any]]:
        def _read() -> list[dict[str, Any]]:
            with self._session_factory() as db:
                stmt = (
                    select(DrillAttempt)
                    .where(DrillAttempt.session_id == session_id)
                    .order_by(DrillAttempt.created_at)
                )
                out: list[dict[str, Any]] = []
                for row in db.scalars(stmt).all():
                    out.append(
                        {
                            "id": row.id,
                            "session_id": row.session_id,
                            "error_entry_id": row.error_entry_id,
                            "target_text": row.target_text,
                            "attempt_number": row.attempt_number,
                            "accuracy_score": row.accuracy_score,
                            "completeness_score": row.completeness_score,
                            "fluency_score": row.fluency_score,
                            "scoring_mode": row.scoring_mode,
                            "passed": row.passed,
                            "learner_audio_path": row.learner_audio_path,
                            "created_at": row.created_at.isoformat(),
                        }
                    )
                return out

        return await asyncio.to_thread(_read)

    async def acknowledge_error(self, error_id: str) -> bool:
        def _write() -> bool:
            with self._session_factory() as db:
                err = db.get(ErrorEntry, error_id)
                if err is None:
                    return False
                if err.acknowledged_at is None:
                    err.acknowledged_at = datetime.now(timezone.utc)
                    db.commit()
                return True

        return await asyncio.to_thread(_write)

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        def _read() -> dict[str, Any] | None:
            with self._session_factory() as db:
                session = db.get(Session, session_id)
                if session is None:
                    return None
                ctx = db.scalar(
                    select(LessonContext).where(LessonContext.session_id == session_id)
                )
                return {
                    "id": session.id,
                    "room_name": session.room_name,
                    "topic_id": session.topic_id,
                    "created_at": session.created_at.isoformat(),
                    "lesson_context": {
                        "context_type": ctx.context_type,
                        "context_payload": ctx.context_payload,
                    }
                    if ctx
                    else None,
                }

        return await asyncio.to_thread(_read)
