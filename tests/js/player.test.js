// The tutor's voice on a phone (web/js/player.js): every reply must be heard without pressing Replay.
import {phone, newPhone, freshImport, heard, settle, showPage, statusText, tap, voice} from './fake-browser.js';
import {test} from 'node:test';
import assert from 'node:assert/strict';

const sentence = text => new TextEncoder().encode(text);
const HINT = 'Tap anywhere to hear the reply.';

/** A page that has just loaded on a phone, with its player set up. */
async function page(options) {
  newPhone(options);
  const player = await freshImport('player.js');
  const util = await import('../../web/js/util.js');
  player.setupPlayer();
  player.stopAudio();   // no request for a tap left over from an earlier test
  return {player, util};
}

/** The voice finishes the sentence it's playing. */
async function finishSentence() {
  voice().finish();
  await settle();
}

test('sentences play one after another, in order', async () => {
  const {player} = await page({strict: false});
  player.play(sentence('one'));
  player.play(sentence('two'));
  await settle();
  assert.deepEqual(await heard(), ['one']);
  assert.ok(player.isSpeaking());
  await finishSentence();
  assert.deepEqual(await heard(), ['one', 'two']);
  await finishSentence();
  assert.ok(!player.isSpeaking());
});

test('after one tap, a whole reply plays by itself', async () => {
  const {player} = await page();
  tap();   // tapping the talk button
  await settle();
  for (const text of ['one', 'two', 'three']) player.play(sentence(text));
  await settle();
  await finishSentence();
  await finishSentence();
  assert.deepEqual(await heard(), ['one', 'two', 'three']);
  assert.equal(statusText(), '');
});

test('a refused reply asks for a tap, and the request stays while the text keeps arriving', async () => {
  const {player, util} = await page();
  player.play(sentence('one'));
  await settle();
  assert.deepEqual(await heard(), []);
  assert.equal(statusText(), HINT);
  util.setStatus('');   // what each new piece of the reply's text does
  assert.equal(statusText(), HINT, 'the request for a tap must not be wiped out');
  tap();
  await settle();
  assert.deepEqual(await heard(), ['one'], 'the tap plays the waiting sentence');
  assert.equal(statusText(), '');
});

test('when the phone withdraws permission between turns, the next tap renews it', async () => {
  // The phone that needed Replay: permission was given once, then lost when the microphone opened and closed.
  const {player} = await page();
  tap();
  await settle();
  player.play(sentence('first reply'));
  await settle();
  await finishSentence();
  phone.revoke();   // the microphone opens and closes for the next turn
  tap();            // the tap that ends the learner's turn
  await settle();
  player.play(sentence('second reply'));
  await settle();
  assert.deepEqual(await heard(), ['first reply', 'second reply']);
  assert.equal(statusText(), '');
});

test('a sentence the phone pauses is kept and resumes on a tap', async () => {
  const {player} = await page();
  tap();
  await settle();
  player.play(sentence('one'));
  player.play(sentence('two'));
  await settle();
  voice().interrupt();
  await settle();
  assert.equal(statusText(), HINT);
  assert.ok(player.isSpeaking(), 'the sentences are still waiting');
  tap();
  await settle();
  await finishSentence();
  assert.deepEqual(await heard(), ['one', 'one', 'two'], 'the paused sentence plays again, then the rest');
});

test('the end of a sentence is not mistaken for a pause by the phone', async () => {
  const {player} = await page({strict: false});
  player.play(sentence('one'));
  await settle();
  await finishSentence();
  assert.equal(statusText(), '');
  assert.ok(!player.isSpeaking());
});

test('Stop silences the voice, drops what is waiting, and clears a request for a tap', async () => {
  const {player} = await page();
  const events = [];
  player.onPlayback(e => events.push(e));
  player.play(sentence('one'));
  player.play(sentence('two'));
  await settle();
  assert.equal(statusText(), HINT);
  player.stopAudio();
  assert.ok(!player.isSpeaking());
  assert.equal(statusText(), '');
  assert.deepEqual(events, ['stopped']);
  tap();
  await settle();
  assert.deepEqual(await heard(), [], 'nothing left to play');
});

test('after Stop, audio still on its way is dropped until the next turn', async () => {
  const {player} = await page({strict: false});
  player.setMuted(true);
  player.play(sentence('late'));
  await settle();
  assert.deepEqual(await heard(), []);
  player.setMuted(false);
  player.play(sentence('next turn'));
  await settle();
  assert.deepEqual(await heard(), ['next turn']);
});

test('a tap while the tutor speaks does not interrupt it', async () => {
  const {player} = await page({strict: false});
  player.play(sentence('one'));
  await settle();
  const playing = voice().src;
  tap();
  await settle();
  assert.equal(voice().src, playing);
  assert.equal(voice().paused, false);
});

test('coming back to the page carries on with what is waiting', async () => {
  const {player} = await page();
  player.play(sentence('one'));
  await settle();
  phone.strict = false;   // the phone now allows it
  showPage();
  await settle();
  assert.deepEqual(await heard(), ['one']);
});

test('a sentence that fails to load is skipped', async () => {
  const {player} = await page({strict: false});
  player.play(sentence('broken'));
  player.play(sentence('fine'));
  await settle();
  voice().onerror();
  await settle();
  assert.deepEqual(await heard(), ['broken', 'fine']);
});

test('a sentence the browser cannot play is skipped', async () => {
  const {player} = await page({strict: false});
  phone.fail = 'NotSupportedError';
  player.play(sentence('unplayable'));
  player.play(sentence('fine'));
  await settle();
  assert.deepEqual(await heard(), ['fine']);
  assert.equal(statusText(), '');
});

test('a sentence interrupted before it begins is kept for a tap', async () => {
  const {player} = await page();
  tap();
  await settle();
  phone.fail = 'AbortError';   // the phone paused it before it started
  player.play(sentence('one'));
  await settle();
  assert.equal(statusText(), HINT);
  tap();
  await settle();
  assert.deepEqual(await heard(), ['one']);
});

test('once a sentence plays, an old request for a tap goes away', async () => {
  const {player} = await page();
  player.play(sentence('one'));
  await settle();
  assert.equal(statusText(), HINT);
  phone.strict = false;   // the phone allows it now
  player.play(sentence('two'));   // the next sentence arriving tries again
  await settle();
  assert.deepEqual(await heard(), ['one']);
  assert.equal(statusText(), '');
});

test('the slower voice plays at 0.8x', async () => {
  const {player} = await page({strict: false});
  const {opts} = await import('../../web/js/options.js');
  opts.slow = true;
  player.play(sentence('one'));
  await settle();
  assert.equal(voice().playbackRate, 0.8);
  opts.slow = false;
});

test('the silence used to renew permission is a valid WAV file', async () => {
  await page();
  tap();
  await settle();
  const silence = new Uint8Array(await phone.played[0].arrayBuffer());
  const view = new DataView(silence.buffer);
  const text = (at, n) => String.fromCharCode(...silence.slice(at, at + n));
  assert.equal(text(0, 4), 'RIFF');
  assert.equal(text(8, 8), 'WAVEfmt ');
  assert.equal(text(36, 4), 'data');
  assert.equal(view.getUint32(4, true), silence.length - 8);
  assert.equal(view.getUint32(40, true), silence.length - 44);
  assert.equal(view.getUint32(24, true), 8000);
});
