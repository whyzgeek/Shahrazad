"""One reply from the tutor as it streams in.

The page sees the reply as it's written. Each sentence, as soon as it's finished, is vowelled and handed to the voice,
in order, while the rest is still being written; that is what makes the first audio come quickly.

The vowelling sometimes fixes the spelling of a word as well (a missing hamza, say). Those fixes are applied to the
written reply too, and the page is shown one Arabic line: the vowelled sentences spoken so far, then the rest as written.
"""
import asyncio, time

from .text import clean_text, complete_sentences, speakable, split_sentences
from .vowels import apply_spelling, vowelize


class SpokenReply:
    def __init__(self, send, speak, http, still_current, t_end):
        """send(**event) to the page; speak(vowelled, on_audio) voices one sentence; still_current() is False once a
        newer turn has taken over; t_end is when the learner stopped speaking."""
        self.send, self.speak, self.http, self.still_current, self.t_end = send, speak, http, still_current, t_end
        self.text = ""          # the reply as written so far
        self.first_token = None
        self.spoken = []        # the vowelled sentences given to the voice, kept for Replay
        self.queued = []        # the sentences handed to the voice so far
        self.display = []       # the reply as the page shows it: vowelled where spoken, as written where not
        self.fixes = []         # (sentence, the same sentence with the vowelling's spelling fixes)
        self.covered = 0        # how much of the written reply the display already replaces
        self.timing = {"stt_s": round(time.time() - t_end, 3)}
        self._sentences = asyncio.Queue()
        self._voice = asyncio.create_task(self._voice_sentences())

    def fixed(self, text):
        for old, new in self.fixes:
            text = text.replace(old, new, 1)
        return text

    def _cover(self, piece):
        """Move past this piece in the written reply. Merged fragments aren't exact substrings, but their end is."""
        tail = piece[-20:]
        i = self.fixed(self.text).find(tail, self.covered)
        if i >= 0:
            self.covered = i + len(tail)

    def new_round(self):
        """After a tool call the tutor writes its reply again from the start."""
        self.queued.clear()
        self.spoken.clear()
        self.display.clear()
        self.covered = 0

    async def write(self, text):
        """The reply so far, as the brain streams it."""
        self.first_token = self.first_token or time.time()
        self.text = text
        await self.send(type="assistant", text=self.fixed(text))
        for sentence in complete_sentences(text)[len(self.queued):]:
            self._queue(sentence)

    def _queue(self, sentence):
        self.queued.append(sentence)
        self._sentences.put_nowait(sentence)

    async def _show(self):
        # text: exactly what the voice was given; display: what the page shows in its place.
        await self.send(type="tashkeel", text=" ".join(self.spoken), display=" ".join(self.display), covered=self.covered)

    async def _voice_sentences(self):
        while (sentence := await self._sentences.get()) is not None:
            if not speakable(sentence):   # in a script the Arabic voice can't read
                self.display.append(sentence)
                self._cover(sentence)
                await self.send(type="text_only", text=sentence)
                await self._show()
                continue
            t0 = time.time()
            vowelled = await vowelize(clean_text(sentence), self.http)
            t1 = time.time()
            self.spoken.append(vowelled)
            self.display.append(vowelled)
            fixed = apply_spelling(sentence, vowelled)
            if fixed != sentence:
                self.fixes.append((sentence, fixed))
                await self.send(type="assistant", text=self.fixed(self.text))
            self._cover(fixed)
            await self._show()

            def first_audio():
                if "end_of_speech_to_first_audio_s" not in self.timing:
                    now = time.time()
                    self.timing.update(first_vowel_s=round(t1 - t0, 3), first_voice_s=round(now - t1, 3),
                                       end_of_speech_to_first_audio_s=round(now - self.t_end, 3))
            await self.speak(vowelled, first_audio)
            if not self.still_current():
                return

    async def finish(self):
        """The reply is complete: voice what's left, and wait until it has all been spoken."""
        self.timing["llm_first_token_s"] = round((self.first_token or time.time()) - self.t_end, 3)
        self.timing["llm_done_s"] = round(time.time() - self.t_end, 3)
        final = split_sentences(self.text)
        done = len(self.queued)
        if done and len(final) >= done and final[done - 1] != self.queued[-1]:
            # A short closing fragment joined the last sentence, which is already with the voice: say just the fragment.
            self._sentences.put_nowait(final[done - 1][len(self.queued[-1]):].strip())
        for sentence in final[done:]:
            self._sentences.put_nowait(sentence)
        self._sentences.put_nowait(None)
        await self._voice
        self.text = self.fixed(self.text)

    def close(self):
        self._voice.cancel()
