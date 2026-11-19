// "Repeat after me" (web/js/drill.js and its use in player.js): where a reply's audio is cut, and the pauses for the
// learner to repeat each phrase.
import {phone, newPhone, freshImport, heard, settle, statusText, tap, voice} from './fake-browser.js';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {cutPoints, pauseAfter, wav, wordCount} from '../../web/js/drill.js';

const RATE = 16000;

/** Speech-like audio: one 0.3 s tone per word, words joined closely, with a real pause after the words in `pausesAfter`. */
function speech(words, pausesAfter) {
  const out = [];
  for (let w = 0; w < words; w++) {
    for (let i = 0; i < 0.3 * RATE; i++) out.push(0.5 * Math.sin(2 * Math.PI * 220 * i / RATE) * (0.6 + 0.4 * Math.sin(Math.PI * i / (0.3 * RATE))));
    const gap = pausesAfter.includes(w + 1) ? 0.2 : 0.01;
    for (let i = 0; i < gap * RATE; i++) out.push(0);
  }
  return Float32Array.from(out);
}

const wordAt = (samples, cut) => {   // how many words come before a cut, in speech()
  let t = 0, w = 0;
  while (t < cut) t += 0.3 * RATE + 0.01 * RATE, w++;
  return w;
};

test('words are counted as the voice says them, not punctuation', () => {
  assert.equal(wordCount('ذَهَبْتُ إِلَى السُّوقِ ، مَعَ أُخْتِي.'), 5);
});

test('a short sentence stays whole', () => {
  assert.deepEqual(cutPoints(speech(6, [3]), RATE, 6), []);
});

test('a long sentence is cut at its pauses, every 3 to 6 words', () => {
  const samples = speech(14, [4, 9]);
  const cuts = cutPoints(samples, RATE, 14);
  assert.equal(cuts.length, 2);
  const pieces = [0, ...cuts, samples.length];
  for (let i = 0; i < cuts.length; i++) {
    const at = cuts[i] / RATE;
    const quiet = samples.subarray(cuts[i] - 80, cuts[i] + 80).every(v => Math.abs(v) < 1e-6);
    assert.ok(quiet, `the cut at ${at.toFixed(2)} s falls in a pause, not in a word`);
  }
  assert.ok(pieces.slice(1).every((c, i) => (c - pieces[i]) / RATE >= 0.8), 'no piece of a word or two');
});

test('without pauses, a long sentence is still cut, between words', () => {
  const samples = speech(12, []);
  const cuts = cutPoints(samples, RATE, 12);
  assert.ok(cuts.length >= 1);
  for (const c of cuts) {
    const words = wordAt(samples, c);
    assert.ok(words >= 2 && words <= 7, `about 3 to 6 words before the cut, not ${words}`);
  }
});

test('the pause for repeating grows with the phrase, and leaves at least a second', () => {
  assert.ok(pauseAfter(1, 0.8) >= 1);
  assert.ok(pauseAfter(2.5, 0.8) > pauseAfter(1, 0.8));
});

test('a phrase is written as a playable WAV', async () => {
  const blob = wav(new Float32Array(160), RATE);
  const bytes = new Uint8Array(await blob.arrayBuffer());
  assert.equal(new TextDecoder().decode(bytes.slice(0, 4)), 'RIFF');
  assert.equal(bytes.length, 44 + 320);
});

test('Repeat after me plays slowly, waits after each phrase but the last, and a tap goes on', async () => {
  newPhone({strict: false});
  const player = await freshImport('player.js');
  player.setupPlayer();
  player.stopAudio();
  player.setDrill(true);
  for (const text of ['one', 'two']) {   // no audio decoding here, so each sentence stays whole: one phrase each
    player.voiceText(text);
    player.play(new TextEncoder().encode(text));
  }
  await settle();
  await settle();
  assert.deepEqual(await heard(), ['one']);
  assert.equal(voice().playbackRate, 0.8, 'slowly');
  voice().finish();
  await settle();
  assert.deepEqual(await heard(), ['one'], 'the next phrase waits for the learner');
  assert.ok(player.isSpeaking(), 'still under way during the pause');
  assert.match(statusText(), /Your turn/);
  tap();
  await settle();
  assert.deepEqual(await heard(), ['one', 'two'], 'a tap ends the pause');
  assert.equal(statusText(), '');
  player.drillComplete();   // the whole reply has arrived: 'two' is the last phrase
  voice().finish();
  await settle();
  assert.ok(!player.isSpeaking(), 'no pause after the last phrase: the reply ends there');
  assert.equal(statusText(), '');
  player.setDrill(false);
  player.play(new TextEncoder().encode('three'));
  await settle();
  voice().finish();
  await settle();
  assert.equal(voice().playbackRate, phone.slow ? 0.8 : 1);
  assert.ok(!player.isSpeaking(), 'normal replies have no pauses');
});

test('if the reply ends during the last pause, the pause ends with it', async () => {
  newPhone({strict: false});
  const player = await freshImport('player.js');
  player.setupPlayer();
  player.stopAudio();
  player.setDrill(true);
  player.voiceText('one');
  player.play(new TextEncoder().encode('one'));
  await settle();
  await settle();
  voice().finish();
  await settle();
  assert.match(statusText(), /Your turn/, 'more might still come');
  player.drillComplete();
  assert.ok(!player.isSpeaking());
  assert.equal(statusText(), '');
  player.setDrill(false);
});
