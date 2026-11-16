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


def test_word_choice_in_speech_is_shown_but_not_tracked():
    """It may be the hearing's mistake, so it doesn't count towards the level or follow-ups; typed, it does."""
    found = [{"wrong": "السوق", "right": "المتجر", "concept": "word_choice"}]
    assert [e["tracked"] for e in learner.clean_errors("ذهبت إلى السوق", found, "voice")] == [False]
    assert [e["tracked"] for e in learner.clean_errors("ذهبت إلى السوق", found, "typed")] == [True]


def test_untracked_cards_leave_the_progress_alone(rec):
    sid = rec.start_session()
    turn = rec.add_turn(sid, "voice", "ذهبت إلى السوق", "نقول: ذهبت إلى المتجر.", None, [])
    rows = rec.add_errors(turn, [{"wrong": "السوق", "right": "المتجر", "concept": "word_choice", "tracked": False}])
    assert rows[0]["tracked"] is False and rec.session_errors(sid)
    assert not [c for c in rec.progress()["practising"] if c["key"] == "word_choice"]
    rec.dismiss(rows[0]["id"])   # "That's not what I said" still works
    assert not rec.session_errors(sid)


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


def test_cards_follow_the_tutors_reply():
    """With the reply, the cards are the tutor's own corrections, so they match the chat."""
    import asyncio
    said = "أنا أظن أن هم يظنون أن جاسوس تدخلت حياته"
    found = {"errors": [
        {"wrong": "أن هم", "right": "أنهم", "concept": "pronoun"},
        {"wrong": "جاسوس", "right": "جاسوسة", "concept": "adjective_gender"},
        {"wrong": "تدخلت حياته", "right": "تدخل حياته", "concept": "verb_subject_agreement"},   # the tutor said otherwise
    ], "concepts": [{"n": 1, "concept": "pronoun"}, {"n": 2, "concept": "adjective_gender"}, {"n": 3, "concept": "preposition"}], "correct_uses": [], "level": "intermediate", "struggling": False}

    async def check(reply, answer=found):
        async with fake_brain(json.dumps(answer, ensure_ascii=False)) as h:
            errors, *_ = await learner.find_errors(said, "", h, "voice", (), reply)
        return [(e["wrong"], e["right"], e["concept"]) for e in errors]
    recast = "نقول: أنا أظن أنهم يظنون أن جاسوسة تدخلت في حياته.\n\nهل تعتقد ذلك؟"
    assert asyncio.run(check(recast)) == [("أن هم", "أنهم", "pronoun"), ("جاسوس", "جاسوسة", "adjective_gender"),
                                          ("تدخلت", "تدخلت في", "preposition")], "each change the tutor made, labelled"
    assert asyncio.run(check(recast, {**found, "concepts": [{"n": 1, "concept": "pronunciation"}, {"n": 2, "concept": "style"}, {"n": 3, "concept": "preposition"}]})) == [
        ("أن هم", "أنهم", "pronunciation"), ("تدخلت", "تدخلت في", "preposition")], "a rephrasing is no mistake"
    async def cards(reply, answer):
        async with fake_brain(json.dumps(answer, ensure_ascii=False)) as h:
            return (await learner.find_errors(said, "", h, "voice", (), reply))[0]
    unlabelled = asyncio.run(check(recast, {**found, "concepts": [{"n": 1, "concept": "pronoun"}, {"n": 3, "concept": "style"}]}))
    assert unlabelled == [("أن هم", "أنهم", "pronoun"), ("جاسوس", "جاسوسة", "other")], "a change left unlabelled still gets a card"
    heard = asyncio.run(cards(recast, {**found, "concepts": [{"n": 1, "concept": "pronunciation"}, {"n": 2, "concept": "style"}, {"n": 3, "concept": "style"}]}))
    assert [e["tracked"] for e in heard] == [False], "a misheard word may be the learner's or the hearing's: shown, not counted"
    assert asyncio.run(check("هذا رأي مثير. لماذا تظن ذلك؟")) == [], "the tutor corrected nothing"
    assert [e[0] for e in asyncio.run(check("انتبه إلى كلمة «جاسوس». هل هي مذكر أم مؤنث؟"))] == ["جاسوس"], "a hint names the word"
    assert len(asyncio.run(check(None))) == 3, "without the reply, everything found counts (evals/errors.py)"


def test_tutor_changes_line_the_correction_up_with_what_was_said():
    changes = learner.tutor_changes
    assert changes("نص", "جواب بلا تصحيح") is None
    # Only part of what was said is corrected: the rest is not a change. Close forms pair up; a dropped word joins its neighbour.
    said = "أنا أظن هذه التصميم مرتبطة أن هم أرادوا تمثيل هذه المكان إلى جنة في القرآن"
    assert changes(said, "نقول: أرادوا تمثيل هذا المكان كجنة في القرآن.\n\nسؤال؟") == [("هذه", "هذا"), ("إلى جنة", "كجنة")]
    said = "هم قاموا تشكيل هذه خطة جميلة أن توجد كم مبرد تشتغل كمبرد"
    assert changes(said, "نقول: قاموا بتشكيل هذه الخطة الجميلة لتعمل كمبرد.") == [
        ("تشكيل", "بتشكيل"), ("خطة جميلة", "الخطة الجميلة"), ("تشتغل", "لتعمل")]
    assert changes("نعم أنا سأعتذر لموظفي", "نقول: نعم، سأعتذر لموظفيَّ.") == [("نعم أنا", "نعم")], "vowel marks are no change"
    assert changes("كلام", "نقول: شيء آخر تماما") == [], "nothing lines up"
