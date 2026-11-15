"""One reply as it streams in (tools/reply.py): each finished sentence goes to the voice in order, while the rest is
still being written, and the page is shown what was spoken."""
import asyncio

import pytest

from tools import reply as reply_module
from tools.reply import SpokenReply

FATHA = "\u064e"
# Three sentences long enough to stand alone: one- and two-word fragments are joined to the next (tools/text.py).
S1, S2, S3 = "أهلا بك يا صديقي.", "كيف حالك هذا الصباح؟", "أنا بخير والحمد لله."
REPLY = " ".join((S1, S2, S3))


def vowelled(text):
    return " ".join(w[0] + FATHA + w[1:] for w in text.split())


class Recorder:
    """The page and the voice, as a reply sees them."""

    def __init__(self, current=True):
        self.events, self.spoken, self.current = [], [], current

    async def send(self, **event):
        self.events.append(event)

    async def speak(self, text, on_audio):
        self.spoken.append(text)
        on_audio()

    def of(self, kind):
        return [e for e in self.events if e["type"] == kind]


@pytest.fixture(autouse=True)
def fake_vowels(monkeypatch):
    async def vowelize(text, http):
        await asyncio.sleep(0)
        return vowelled(text)
    monkeypatch.setattr(reply_module, "vowelize", vowelize)


def stream(text, recorder, t_end=0):
    """Write the reply word by word, as the brain streams it, and finish it."""
    async def main():
        r = SpokenReply(recorder.send, recorder.speak, None, lambda: recorder.current, t_end)
        words = text.split(" ")
        for i in range(1, len(words) + 1):
            await r.write(" ".join(words[:i]))
            await asyncio.sleep(0)
        await r.finish()
        return r
    return asyncio.run(asyncio.wait_for(main(), 10))


def test_each_sentence_is_vowelled_and_spoken_in_order():
    rec = Recorder()
    r = stream(REPLY, rec)
    assert rec.spoken == [vowelled(S1), vowelled(S2), vowelled(S3)]
    assert r.spoken == rec.spoken, "kept for Replay"
    assert rec.of("assistant")[-1]["text"] == REPLY
    assert rec.of("tashkeel")[-1]["display"] == " ".join(rec.spoken)
    assert {"stt_s", "llm_first_token_s", "llm_done_s", "end_of_speech_to_first_audio_s"} <= set(r.timing)


def test_voice_starts_before_the_reply_is_finished():
    rec = Recorder()
    order = []

    async def speak(text, on_audio):
        order.append(("spoke", text))
        on_audio()

    async def main():
        r = SpokenReply(rec.send, speak, None, lambda: True, 0)
        await r.write(S1 + " كيف")
        for _ in range(5):
            await asyncio.sleep(0)
        order.append(("still writing", None))
        await r.write(S1 + " " + S2)
        await r.finish()
    asyncio.run(asyncio.wait_for(main(), 10))
    assert order[0] == ("spoke", vowelled(S1))
    assert order[1] == ("still writing", None)


def test_a_sentence_in_another_script_is_shown_not_spoken():
    rec = Recorder()
    stream(f"{S1} This is English only. {S2}", rec)
    assert rec.spoken == [vowelled(S1), vowelled(S2)]
    assert rec.of("text_only") == [{"type": "text_only", "text": "This is English only."}]


def test_a_spelling_fix_from_the_vowelling_reaches_the_written_reply(monkeypatch):
    async def vowelize(text, http):
        return text.replace("اصدقائي", "أَصدقائي")   # the vowelling adds the missing hamza
    monkeypatch.setattr(reply_module, "vowelize", vowelize)
    rec = Recorder()
    r = stream("ذهبت مع اصدقائي إلى البحر.", rec)
    assert r.text == "ذهبت مع أصدقائي إلى البحر."
    assert rec.of("assistant")[-1]["text"] == r.text


def test_a_newer_turn_stops_the_voice():
    rec = Recorder(current=False)   # the learner already started talking again
    stream(REPLY, rec)
    assert rec.spoken == [vowelled(S1)]


def test_a_tool_call_starts_the_reply_again():
    rec = Recorder()

    async def main():
        r = SpokenReply(rec.send, rec.speak, None, lambda: True, 0)
        await r.write("سأبحث عن ذلك الآن.")
        r.new_round()
        assert r.queued == [] and r.spoken == [] and r.covered == 0
        await r.write("وجدت الخبر الذي تريده.")
        await r.finish()
    asyncio.run(asyncio.wait_for(main(), 10))
    assert rec.spoken == [vowelled("وجدت الخبر الذي تريده.")]


def test_a_short_closing_fragment_is_still_spoken():
    rec = Recorder()
    stream(f"{S1} {S2} شكرا.", rec)
    assert rec.spoken == [vowelled(S1), vowelled(S2), vowelled("شكرا")], "the fragment alone, not its sentence twice"


def test_close_cancels_the_voice():
    rec = Recorder()

    async def main():
        r = SpokenReply(rec.send, rec.speak, None, lambda: True, 0)
        r.close()
        await asyncio.sleep(0)
        assert r._voice.cancelled()
    asyncio.run(asyncio.wait_for(main(), 10))
