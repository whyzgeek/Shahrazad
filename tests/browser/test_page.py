"""The page itself, in headless Chromium sized and behaving like a phone, against the real app and fake models.

These catch what the other tests can't: the page's scripts working together in a real browser. Above all, every reply
must be heard on a phone without pressing Replay (tests/browser/phone_rules.js gives Chromium a phone's rules).

Needs Playwright's Python package and its Chromium (pip install playwright; playwright install chromium); the tests
are skipped without them.
"""
import json
from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api")

from fakes.backends import CORRECTION, MISTAKE, REPLY, TITLE

PHONE_RULES = (Path(__file__).parent / "phone_rules.js").read_text()
TAP_HINT = "Tap anywhere to hear the reply."
WAIT_MS = 20000
PHONE = {"viewport": {"width": 390, "height": 844}, "is_mobile": True, "has_touch": True}


@pytest.fixture(scope="module")
def browser():
    with playwright.sync_playwright() as p:
        try:
            b = p.chromium.launch(args=["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"])
        except playwright.Error as e:
            pytest.skip(f"Chromium for Playwright isn't installed ({e.message.splitlines()[0]})")
        yield b
        b.close()


class Page:
    """One open page, with the page's script errors collected."""

    def __init__(self, browser, tutor, **device):
        self.touch = device.get("has_touch", False)
        self.context = browser.new_context(permissions=["microphone"], **device)
        self.context.add_init_script(PHONE_RULES)
        self.pg = self.context.new_page()
        self.errors = []
        self.pg.on("pageerror", lambda e: self.errors.append(str(e)))
        self.pg.on("console", lambda m: m.type == "error" and self.errors.append(m.text))
        self.pg.on("dialog", lambda d: d.accept(TITLE) if d.type == "prompt" else d.accept())
        self.pg.goto(tutor.url + "/")
        self.pg.wait_for_selector("#talk:not([disabled])", timeout=WAIT_MS)

    def tap(self, selector):
        """A real tap (or click), which the phone counts as the learner's."""
        if self.touch:
            self.pg.tap(selector)
        else:
            self.pg.click(selector)

    def tap_anywhere(self):
        """A tap on a part of the page that does nothing itself (the conversation's title)."""
        self.tap("#ctitle")

    def phone(self, name):
        return self.pg.evaluate(f"window.phone.{name}")

    def wait_for_sentences(self, n):
        try:
            self.pg.wait_for_function(f"window.phone.sentences >= {n}", timeout=WAIT_MS)
        except playwright.TimeoutError:
            raise AssertionError(f"{self.phone('sentences')} of {n} sentences heard; the phone saw: {self.phone('log')}") from None

    def new_conversation(self):
        """Start a new conversation and wait until the page has loaded it. An empty conversation already shows the
        welcome, so wait for the old page content (marked here) to be replaced, or a turn could be typed into it."""
        self.pg.evaluate("document.querySelector('#log').append(Object.assign(document.createElement('i'), {id: 'old'}))")
        if self.pg.is_visible("#menu"):
            self.tap("#menu")
        self.tap("#newc")
        self.pg.wait_for_selector("#old", state="detached", timeout=WAIT_MS)
        self.pg.wait_for_selector("#welcome", timeout=WAIT_MS)

    def talk(self, seconds=1.0, at=None):
        """One spoken turn, tapping to start and tapping to send, as on a phone. `at` taps that point of the talk button
        (x from its left edge, as a fraction of its width) both times, as a finger would, instead of its centre."""
        if at is None:
            tap = lambda: self.tap("#talk")
        else:
            box = self.pg.locator("#talk").bounding_box()
            point = (box["x"] + box["width"] * at, box["y"] + box["height"] / 2)
            tap = lambda: self.pg.touchscreen.tap(*point)
        tap()
        self.pg.wait_for_function("document.querySelector('#talk').textContent.startsWith('Listening')", timeout=WAIT_MS)
        self.pg.wait_for_timeout(seconds * 1000)
        tap()

    def type_turn(self, text):
        self.pg.fill("#txt", text)
        self.pg.press("#txt", "Enter")

    def turns(self):
        return self.pg.locator(".turn .num").count()

    def wait_for_turn(self, n):
        self.pg.wait_for_selector(f".turn .num:text('#{n}')", timeout=WAIT_MS)

    def status(self):
        return self.pg.inner_text("#st")

    def close(self):
        self.context.close()


@pytest.fixture
def phone(browser, tutor):
    page = Page(browser, tutor, **PHONE)
    page.new_conversation()
    yield page
    assert not page.errors, page.errors
    page.close()


@pytest.fixture
def desktop(browser, tutor):
    page = Page(browser, tutor, viewport={"width": 1280, "height": 860})
    page.new_conversation()
    yield page
    assert not page.errors, page.errors
    page.close()


# ------------------------------------------------------------ hearing the tutor on a phone
def test_phone_talks_by_tapping(phone):
    assert phone.pg.inner_text("#talk") == "Tap to talk"


def test_phone_hears_every_reply_without_replay(phone):
    phone.talk()
    phone.wait_for_turn(1)
    phone.wait_for_sentences(len(REPLY))
    assert phone.status() != TAP_HINT
    # The next turn, after the phone has taken back its permission (the microphone opened and closed).
    phone.pg.evaluate("window.phone.revoke()")
    phone.talk()
    phone.wait_for_turn(2)
    phone.wait_for_sentences(2 * len(REPLY))
    assert phone.status() != TAP_HINT


def test_tapping_the_right_of_the_talk_button_still_plays_the_reply(phone):
    """A Stop button used to appear beside the talk button as a tap ended the turn, under a finger on its right side,
    and the phone then sent that same tap's click to it, which silenced the whole reply. Phones have no Stop now."""
    phone.talk(at=0.92)
    phone.wait_for_turn(1)
    phone.wait_for_sentences(len(REPLY))


def test_phone_hears_a_typed_turn(phone, tutor):
    phone.type_turn("مرحبا")
    phone.wait_for_turn(1)
    phone.wait_for_sentences(len(REPLY))
    events = [json.loads(l)["event"] for l in (tutor.data / "playback.jsonl").read_text().splitlines()]
    assert {"page", "arrived", "play", "playing", "ended"} <= set(events), "the playback diary reaches the server"


def test_a_sentence_the_phone_pauses_waits_for_a_tap(phone):
    phone.type_turn("مرحبا")
    phone.wait_for_turn(1)   # the whole reply has arrived, so nothing new will start the voice again
    phone.pg.wait_for_function("window.phone.current && !window.phone.current.paused", timeout=WAIT_MS)
    phone.pg.evaluate("window.phone.interrupt()")
    phone.pg.wait_for_function(f"document.querySelector('#st').textContent === {TAP_HINT!r}", timeout=WAIT_MS)
    phone.pg.wait_for_timeout(1000)
    assert phone.status() == TAP_HINT, "the request for a tap stays until it's answered"
    assert phone.phone("sentences") < len(REPLY)
    phone.tap_anywhere()
    phone.wait_for_sentences(len(REPLY))
    assert phone.status() != TAP_HINT


def test_before_any_tap_the_page_asks_for_one(browser, tutor):
    """A reply that arrives on a page nobody has tapped yet: the message is sent by a script, which isn't a tap."""
    page = Page(browser, tutor, **PHONE)
    try:
        page.pg.fill("#txt", "مرحبا")
        page.pg.evaluate("document.querySelector('#f').requestSubmit()")
        page.pg.wait_for_function(f"document.querySelector('#st').textContent === {TAP_HINT!r}", timeout=WAIT_MS)
        assert page.phone("sentences") == 0 and page.phone("refused") > 0
        page.tap_anywhere()
        page.wait_for_sentences(len(REPLY))
        assert not page.errors, page.errors
    finally:
        page.close()


def test_talking_again_interrupts_the_tutor(phone):
    phone.type_turn("مرحبا")
    phone.pg.wait_for_function("window.phone.current && !window.phone.current.paused", timeout=WAIT_MS)
    phone.tap("#talk")
    phone.pg.wait_for_function("document.querySelector('#talk').textContent.startsWith('Listening')", timeout=WAIT_MS)
    heard = phone.phone("sentences")
    phone.pg.wait_for_timeout(1500)
    assert phone.phone("sentences") == heard < len(REPLY), "nothing more of the reply plays once the learner talks"
    phone.tap("#talk")


def test_phone_has_no_stop_button(phone):
    phone.type_turn("مرحبا")
    phone.pg.wait_for_function("window.phone.current && !window.phone.current.paused", timeout=WAIT_MS)
    assert phone.pg.is_hidden("#stop")


def test_stop_button_silences_the_tutor_on_a_laptop(desktop):
    desktop.type_turn("مرحبا")
    desktop.pg.wait_for_selector("#stop:not([hidden])", timeout=WAIT_MS)
    desktop.pg.wait_for_function("window.phone.current && !window.phone.current.paused", timeout=WAIT_MS)
    desktop.pg.wait_for_timeout(700)   # a real press comes after Stop has settled (web/js/talk.js: STOP_SETTLE_MS)
    desktop.pg.click("#stop")
    desktop.pg.wait_for_timeout(1500)
    assert desktop.phone("sentences") < len(REPLY)
    assert desktop.pg.is_hidden("#stop")


def test_esc_silences_the_tutor(desktop):
    desktop.type_turn("مرحبا")
    desktop.pg.wait_for_function("window.phone.current && !window.phone.current.paused", timeout=WAIT_MS)
    desktop.pg.keyboard.press("Escape")
    desktop.pg.wait_for_timeout(1500)
    assert desktop.phone("sentences") < len(REPLY)
    assert desktop.pg.inner_text("#talk").startswith("Hold to talk")


def test_phone_cards_open_from_a_mistake(phone):
    phone.type_turn(f"أكلت {MISTAKE}")
    phone.wait_for_turn(1)
    phone.pg.wait_for_selector("mark.err", timeout=WAIT_MS)
    assert phone.pg.is_hidden("#notes") or not phone.pg.evaluate("document.body.classList.contains('cards')")
    phone.tap("mark.err")
    phone.pg.wait_for_function("document.body.classList.contains('cards')", timeout=WAIT_MS)
    assert CORRECTION in phone.pg.locator("#notelist").text_content()
    phone.tap("#nclose")
    assert not phone.pg.evaluate("document.body.classList.contains('cards')")


# ------------------------------------------------------------ the rest of the page, on a laptop-sized screen
def test_a_whole_session(desktop, tutor):
    pg = desktop.pg
    assert pg.inner_text("#talk") == "Hold to talk (or hold the space bar)"
    desktop.type_turn(f"ذهبت إلى السوق واشتريت {MISTAKE}")
    desktop.wait_for_turn(1)
    assert pg.inner_text(".m.bot .ar").replace("َ", "") == " ".join(REPLY)
    assert pg.locator(".m.bot .w").count() >= len(" ".join(REPLY).split())
    desktop.wait_for_sentences(len(REPLY))

    # The correction card, its turn number and lesson.
    pg.wait_for_selector(".note", timeout=WAIT_MS)
    assert CORRECTION in pg.inner_text(".note") and pg.inner_text(".note .tn") == "#1"
    assert pg.locator("mark.err").count()
    pg.click(".note .act button >> nth=0")
    pg.wait_for_selector(".note .lesson", timeout=WAIT_MS)
    assert pg.inner_text(".note .lesson p")

    # Under the reply: translation, a word's meaning, Replay.
    pg.click(".m.bot .translate")
    pg.wait_for_function("document.querySelector('.en')?.textContent === " + repr(TITLE), timeout=WAIT_MS)
    pg.click(".m.bot .w >> nth=1")
    pg.wait_for_function("!document.querySelector('#pop').hidden && document.querySelector('#pop').textContent !== '…'", timeout=WAIT_MS)
    pg.keyboard.press("Escape")
    assert pg.evaluate("document.querySelector('#pop').hidden")
    pg.click(".m.bot .replay")
    pg.wait_for_selector(".replay.on", timeout=WAIT_MS)
    pg.wait_for_selector(".replay:not(.on)", timeout=WAIT_MS)
    assert desktop.phone("sentences") == 2 * len(REPLY)

    # The options: vowel marks off and on, newest first and back.
    has_marks = "/[\\u064b-\\u0652]/.test(document.querySelector('.m.bot .ar').textContent)"
    assert pg.evaluate(has_marks)
    pg.click("#o-marks")
    assert not pg.evaluate(has_marks)
    pg.click("#o-marks")
    assert pg.evaluate(has_marks)
    pg.click("#order")
    assert pg.inner_text("#order") == "Newest first ↑"
    pg.click("#order")

    # Progress and Status.
    pg.click("#progb")
    pg.wait_for_selector("#pcards .note", timeout=WAIT_MS)
    pg.click("#pclose")
    pg.click("#statb")
    pg.wait_for_selector(".part", timeout=WAIT_MS)
    parts = pg.locator(".part").all_inner_texts()
    assert len(parts) == 4 and not any("not answering" in p.lower() for p in parts), parts
    pg.click("#pclose")

    # Conversations: a new one, back to this one with its cards, and a new name.
    desktop.new_conversation()
    assert desktop.turns() == 0
    pg.locator(".sr:not(.cur) .si").first.click()
    desktop.wait_for_turn(1)
    pg.wait_for_selector(".note", timeout=WAIT_MS)
    pg.locator(".sr.cur .ops button >> nth=0").click()
    pg.wait_for_function(f"document.querySelector('#ctitle').textContent === {TITLE!r}", timeout=WAIT_MS)


def test_text_size_on_a_phone(phone):
    pg = phone.pg
    phone.type_turn("مرحبا")
    phone.wait_for_turn(1)
    size = lambda: pg.evaluate("document.querySelector('.m.bot .ar').getBoundingClientRect().height")
    button_width = pg.evaluate("document.querySelector('#talk').getBoundingClientRect().width")
    before = size()
    for _ in range(3):
        phone.tap("#o-larger")
    assert pg.inner_text("#o-size") == "150%" and pg.is_disabled("#o-larger")
    assert size() > before * 1.3, "the reply's text grows"
    assert pg.evaluate("document.querySelector('#talk').getBoundingClientRect().width") == button_width, "the controls don't"
    assert pg.evaluate("document.documentElement.scrollWidth <= innerWidth"), "nothing spills off the side of the phone"
    # A word's meaning still opens beside its word.
    phone.tap(".m.bot .w >> nth=1")
    pg.wait_for_function("!document.querySelector('#pop').hidden && document.querySelector('#pop').textContent !== '…'", timeout=WAIT_MS)
    word = pg.locator(".m.bot .w >> nth=1").bounding_box()
    pop = pg.locator("#pop").bounding_box()
    assert abs((pop["y"] + pop["height"]) - word["y"]) < 40 or abs(pop["y"] - (word["y"] + word["height"])) < 40
    # Remembered after a reload.
    pg.reload()
    pg.wait_for_selector("#talk:not([disabled])", timeout=WAIT_MS)
    assert pg.inner_text("#o-size") == "150%"
    for _ in range(4):
        phone.tap("#o-smaller")
    assert pg.inner_text("#o-size") == "85%" and pg.is_disabled("#o-smaller")


def test_starter_button_begins_a_conversation(desktop):
    desktop.pg.click("#welcome .starts button >> nth=0")
    desktop.wait_for_turn(1)
    desktop.wait_for_sentences(len(REPLY))
