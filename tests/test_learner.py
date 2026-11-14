"""The learner record: error filtering, sessions, the follow-up schedule and the word-meaning cache."""
import json, time
import pytest
from tools import learner

CONCEPT = next(c for c in learner.CONCEPTS if c not in learner.NOT_IN_SPEECH and c != "misheard")


@pytest.fixture
def rec(tmp_path):
    return learner.Learner(tmp_path / "l.db")


def test_normal():
    assert learner.normal("إِلَى المدرسةِ!") == "الي المدرسه"


def test_clean_errors_keeps_only_real_quotes():
    said = "أمس أنا يذهب إلى السوق"
    found = [{"wrong": "أنا يذهب", "right": "ذهبت", "concept": CONCEPT},
             {"wrong": "لم يقل هذا", "right": "شيء آخر", "concept": CONCEPT},   # not in what was said
             {"wrong": "السوق", "right": "السوق", "concept": CONCEPT},          # no change
             {"wrong": "يذهب", "right": "ذهب", "concept": CONCEPT},             # overlaps the first
             {"wrong": "أمس", "right": "البارحة", "concept": "misheard"}]
    out = learner.clean_errors(said, found, "typed")
    assert [e["wrong"] for e in out] == ["أنا يذهب"]
    assert out[0]["tracked"]


def test_clean_errors_skips_written_only_concepts_in_speech():
    found = [{"wrong": "السوق", "right": "المتجر", "concept": "word_choice"}]
    assert learner.clean_errors("ذهبت إلى السوق", found, "voice") == []
    assert len(learner.clean_errors("ذهبت إلى السوق", found, "typed")) == 1


def test_sessions_rename_and_delete(rec):
    sid = rec.start_session()
    turn = rec.add_turn(sid, "typed", "مرحبا", "أهلاً", None, ["أَهْلًا"])
    rec.add_errors(turn, [{"wrong": "x", "right": "y", "concept": CONCEPT, "tracked": True}])
    assert rec.session_turns(sid)[0]["spoken"] == "أَهْلًا"
    rec.save_session(sid, "Old name", json.dumps({"titled": False}))
    rec.rename_session(sid, "My name")
    row = rec.load_session(sid)
    assert row["title"] == "My name" and json.loads(row["state"])["titled"] is True
    rec.delete_session(sid)
    assert rec.load_session(sid) is None and rec.session_turns(sid) == [] and rec.session_errors(sid) == []
    assert CONCEPT in rec.practising()   # what was practised stays


def test_review_schedule(rec):
    rec.add_errors(rec.add_turn(rec.start_session(), "typed", "a", "b", None, []), [{"wrong": "x", "right": "y", "concept": CONCEPT, "tracked": True}])
    step = lambda: rec.db.execute("SELECT step, due_at FROM concepts WHERE concept=?", (CONCEPT,)).fetchone()
    rec.review_result(CONCEPT, True)
    s, due = step()
    assert s == 1 and due == pytest.approx(time.time() + learner.INTERVAL_DAYS[0] * 86400, abs=5)
    rec.review_result(CONCEPT, False)
    s, due = step()
    assert s == 0 and due == pytest.approx(time.time() + 86400, abs=5)


def test_learned_after_free_use_on_two_days(rec, monkeypatch):
    rec.add_errors(rec.add_turn(rec.start_session(), "typed", "a", "b", None, []), [{"wrong": "x", "right": "y", "concept": CONCEPT, "tracked": True}])
    status = lambda: rec.db.execute("SELECT status FROM concepts WHERE concept=?", (CONCEPT,)).fetchone()[0]
    real = learner.time.strftime
    for day in ("2026-01-01", "2026-01-01", "2026-01-02"):
        monkeypatch.setattr(learner.time, "strftime", lambda f, d=day: d)
        rec.record_free_use([CONCEPT])
        if day == "2026-01-01":
            assert status() == "practising"
    monkeypatch.setattr(learner.time, "strftime", real)
    assert status() == "learned"


def test_gloss_cache(rec):
    assert rec.gloss("كتاب", "هذا كتاب") is None
    rec.save_gloss("كتاب", "هذا كتاب", "book", "كِتَاب")
    assert rec.gloss("كتاب", "هذا كتاب") == {"meaning": "book", "base": "كِتَاب"}
    assert rec.gloss("كتاب", "جملة أخرى") is None


def fake_brain(*contents):
    """An httpx client whose brain answers with these message contents, in order."""
    import httpx
    replies = iter(contents)
    handler = lambda req: httpx.Response(200, json={"choices": [{"message": {"content": next(replies)}}]})
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_check_target_retries_broken_json():
    import asyncio
    async def go():
        async with fake_brain('{"used": true, "corr', '{"used": true, "correct": true}') as h:
            return await learner.check_target("نص", CONCEPT, h)
    assert asyncio.run(go()) is True


def test_find_errors_gives_up_after_two_broken_answers():
    import asyncio
    async def go():
        async with fake_brain("not json", '{"level": "beginner"}') as h:
            return await learner.find_errors("نص", "", h, "typed")
    with pytest.raises(ValueError):
        asyncio.run(go())
