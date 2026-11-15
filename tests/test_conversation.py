"""Whole conversations with the real app, over its WebSocket as the page holds them, against fake models.

Each test checks what the page would receive: the reply's text, its vowelled text, one piece of audio per sentence,
the saved turn, and the events for Replay, Stop and the conversation list.
"""
import asyncio, json, math, struct

import re

import httpx, pytest, websockets

from fakes.backends import HEARD, REPLY, TITLE

WAIT_S = 15   # longest any single expected event may take
bare = lambda text: re.sub("[\u064b-\u0652]", "", text)   # without vowel marks


class Page:
    """One open page: sends events like web/js/connection.js and collects what the server sends back."""

    def __init__(self, ws):
        self.ws, self.events, self.audio = ws, [], 0

    async def send(self, kind, **fields):
        await self.ws.send(json.dumps({"type": kind, **fields}, ensure_ascii=False))

    async def until(self, kind, wait=WAIT_S):
        """Receive until an event of this kind arrives, and return it. Audio is counted on the way."""
        async def read():
            while True:
                m = await self.ws.recv()
                if isinstance(m, bytes):
                    self.audio += 1
                    continue
                event = json.loads(m)
                self.events.append(event)
                if event["type"] == kind:
                    return event
        return await asyncio.wait_for(read(), wait)

    async def new_conversation(self):
        """Start a new conversation, as the sidebar's New button does, and return its id."""
        await self.send("reset")
        return await self.loaded()

    async def loaded(self):
        """A conversation arrives with the list of conversations right after it."""
        conversation = await self.until("session")
        await self.until("sessions")
        return conversation["id"]

    def seen(self, kind):
        return [e for e in self.events if e["type"] == kind]


def run(tutor, scenario):
    async def main():
        async with websockets.connect(tutor.ws_url, max_size=None) as ws:
            page = Page(ws)
            await page.loaded()
            await scenario(page)
    asyncio.run(asyncio.wait_for(main(), 120))


def speech(seconds=1.0, rate=16000):
    """A tone as 16 kHz PCM, in the 80 ms chunks the page's microphone sends."""
    pcm = b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 220 * i / rate))) for i in range(int(seconds * rate)))
    return [pcm[i:i + 2560] for i in range(0, len(pcm), 2560)]


@pytest.fixture(autouse=True)
def fresh_calls(tutor):
    tutor.reset_calls()


def test_opening_the_page_lists_conversations_and_loads_the_latest(tutor):
    async def scenario(page):
        assert page.seen("sessions") and page.seen("session")
    run(tutor, scenario)


def test_typed_turn_is_written_vowelled_spoken_and_saved(tutor):
    async def scenario(page):
        await page.new_conversation()
        await page.send("text", text="مرحبا")
        turn = await page.until("turn")
        timing = await page.until("timing")
        assert page.seen("assistant")[-1]["text"] == " ".join(REPLY)
        shown = page.seen("tashkeel")[-1]["display"]
        assert bare(shown) == " ".join(REPLY) and shown != " ".join(REPLY), "the reply is shown with its vowels"
        assert page.audio == len(REPLY), "one piece of audio per sentence"
        assert turn["n"] == 1 and turn["id"] > 0
        assert timing["end_of_speech_to_first_audio_s"] >= 0
    run(tutor, scenario)
    assert [bare(c["text"]) for c in tutor.calls("voice")] == REPLY


def test_spoken_turn_is_heard_then_answered(tutor):
    async def scenario(page):
        await page.send("start")
        for chunk in speech():
            await page.ws.send(chunk)
        await page.send("stop")
        final = await page.until("final")
        assert final["text"] == HEARD
        assert page.seen("partial"), "the words show while the learner speaks"
        await page.until("timing")
        assert page.audio == len(REPLY)
    run(tutor, scenario)
    assert tutor.calls("hearing")[0]["chunks"] == len(speech())


def test_a_turn_with_no_speech_says_so(tutor):
    async def scenario(page):
        await page.send("start")
        await page.send("stop")
        assert (await page.until("final"))["text"] == ""
        assert "No speech" in (await page.until("error"))["text"]
    run(tutor, scenario)
    assert not tutor.calls("voice")


def test_replay_speaks_the_saved_reply_again(tutor):
    async def scenario(page):
        await page.send("text", text="مرحبا")
        turn = await page.until("turn")
        await page.until("timing")
        heard = page.audio
        await page.send("replay", turn=turn["id"])
        await page.until("replay_done")
        assert page.audio - heard == len(REPLY)
    run(tutor, scenario)


def test_stop_ends_the_reply_before_it_is_saved(tutor):
    async def scenario(page):
        await page.send("text", text="مرحبا")
        await page.send("cancel")
        with pytest.raises(asyncio.TimeoutError):
            await page.until("turn", wait=3)
    run(tutor, scenario)


def test_new_rename_switch_and_delete(tutor):
    async def scenario(page):
        first = await page.new_conversation()
        await page.send("text", text="مرحبا")
        await page.until("timing")
        assert await page.new_conversation() != first
        await page.send("rename", id=first, title="  أول   محادثة ")
        listed = {s["id"]: s["title"] for s in (await page.until("sessions"))["sessions"]}
        assert listed[first] == "أول محادثة"
        await page.send("switch", id=first)
        assert await page.loaded() == first
        assert page.seen("session")[-1]["turns"][0]["reply"] == " ".join(REPLY)
        await page.send("delete", id=first)
        assert await page.loaded() != first   # deleting the open conversation starts a new one
        remaining = {s["id"] for s in (await page.until("sessions"))["sessions"]}
        assert first not in remaining
        await page.send("switch", id=first)
        assert "no longer exists" in (await page.until("error"))["text"]
    run(tutor, scenario)


def test_the_playback_diary_is_saved(tutor):
    async def scenario(page):
        await page.send("playback", event="refused", error="NotAllowedError", ms=12)
        await page.send("text", text="مرحبا")   # the next event is handled after the diary line
        await page.until("turn")
    run(tutor, scenario)
    lines = [json.loads(l) for l in (tutor.data / "playback.jsonl").read_text().splitlines()]
    assert {"event": "refused", "error": "NotAllowedError", "ms": 12}.items() <= lines[-1].items()
    assert "type" not in lines[-1] and lines[-1]["conversation"] > 0


def test_page_and_routes(tutor):
    page = httpx.get(tutor.url + "/", timeout=10)
    assert page.status_code == 200 and 'type="module"' in page.text
    for path in ("/web/js/main.js", "/web/js/player.js", "/web/style.css"):
        r = httpx.get(tutor.url + path, timeout=10)
        assert r.status_code == 200 and r.headers["cache-control"] == "no-cache", path
    health = httpx.get(tutor.url + "/health", timeout=10).json()
    assert all(part["ok"] for part in health.values()), health
    status = httpx.get(tutor.url + "/status", timeout=10).json()
    assert {p["kind"] for p in status["parts"]} == {"brain", "hearing", "voice"} and status["credit"] is None
    progress = httpx.get(tutor.url + "/progress", timeout=10).json()
    assert {"band", "turns", "practising", "learned", "cards"} <= set(progress)
    assert httpx.get(tutor.url + "/cards.csv", timeout=10).headers["content-type"].startswith("text/csv")
    assert httpx.get(tutor.url + "/lesson/no-such-rule", timeout=10).status_code == 404


def test_gloss_and_translate_use_the_brain(tutor):
    gloss = httpx.post(tutor.url + "/gloss", json={"word": "صديقي", "sentence": REPLY[0]}, timeout=10)
    assert gloss.status_code == 200 and set(gloss.json()) == {"meaning", "base"}
    assert httpx.post(tutor.url + "/gloss", json={"word": "hello", "sentence": "hello"}, timeout=10).status_code == 400
    translated = httpx.post(tutor.url + "/translate", json={"text": REPLY[0]}, timeout=10)
    assert translated.json() == {"english": TITLE}
    assert httpx.post(tutor.url + "/translate", json={"text": "hello"}, timeout=10).status_code == 400
