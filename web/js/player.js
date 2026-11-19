// The tutor's voice: one audio element plays the sentences in order as they arrive.
//
// Phones treat an audio element like a music player: at media volume, and once a tap has started it, it may go on
// playing new sentences by itself. (Web Audio was paused by phones whenever the microphone opened or closed, so replies
// needed Replay.) A phone can still withdraw that permission, for instance when the microphone opens or closes, so
// every tap renews it with a moment of silence. If the phone refuses or pauses a sentence anyway, the sentence is kept
// and the page asks for a tap, which plays it.
import {note} from './diary.js';
import {pauseAfter, split} from './drill.js';
import {opts} from './options.js';
import {pinStatus} from './util.js';

const SILENCE = URL.createObjectURL(silentWav(0.05));

let player = null;
let current = null;      // the sentence playing now
let waiting = [];        // object URLs of the sentences still to play
let muted = false;       // after Stop, audio still on its way is dropped
const listeners = [];
// "Repeat after me" (drill.js): each sentence comes with its text, is cut into phrases, and every phrase is followed
// by a pause for the learner to say it. A tap during the pause goes on at once.
const DRILL_RATE = 0.8;
let drill = false;
let drillTexts = [];     // the text of each sentence still to arrive
let drilled = new Set(); // the queued phrases that are followed by a pause
let cutting = Promise.resolve();   // phrases are queued in the order their sentences arrived
let cuttingCount = 0;
let gap = null;          // the pause after a phrase
let drillSent = false;   // all of the reply has arrived: its last phrase needs no pause, the reply ends there
let session = 0;         // a Stop makes phrases still being cut obsolete

/** Call fn('ended') after each sentence, and fn('stopped') when playback is stopped. */
export const onPlayback = fn => listeners.push(fn);
const emit = event => listeners.forEach(fn => fn(event));

export const isSpeaking = () => current !== null || waiting.length > 0 || gap !== null || cuttingCount > 0;

/** Play the next sentences as "Repeat after me", or normally again. */
export function setDrill(value) {
  drill = value;
  drillTexts = [];
  drillSent = false;
}

/** All of the reply has arrived. If the pause after its last phrase has already begun, it ends now. */
export function drillComplete() {
  drillSent = true;
  if (gap !== null && !waiting.length && !cuttingCount) {
    endGap();
    emit('ended');
  }
}

const lastPhrase = () => drillSent && !waiting.length && !cuttingCount;

/** The text of the next sentence to arrive, in "Repeat after me". */
export function voiceText(text) {
  if (drill) drillTexts.push(text);
}

/** Drop voice that is still arriving (after Stop), or accept it again (a new turn). */
export function setMuted(value) {
  muted = value;
}

/** Queue one sentence of the tutor's voice (WAV or MP3 bytes). */
export function play(bytes) {
  if (muted) return;
  if (drill) return queuePhrases(bytes, drillTexts.shift() || '');
  waiting.push(URL.createObjectURL(new Blob([bytes])));
  note('arrived', {bytes: bytes.byteLength, waiting: waiting.length, playing: current !== null});
  playNext();
}

function queuePhrases(bytes, text) {
  const mine = session;
  cuttingCount++;
  cutting = cutting.then(async () => {
    let pieces = null;
    try {
      pieces = await split(bytes, text);
    } catch (e) {
      note('could not cut', {error: e.name});
    }
    if (mine !== session || muted) return;
    for (const piece of pieces || [{blob: new Blob([bytes])}]) {
      const url = URL.createObjectURL(piece.blob);
      waiting.push(url);
      drilled.add(url);
    }
    note('cut into phrases', {phrases: pieces ? pieces.length : 1});
    playNext();
  }).finally(() => {
    if (mine === session) cuttingCount--;
  });
}

function endGap() {
  clearTimeout(gap);
  gap = null;
  askForTap(false);
}

export function stopAudio() {
  session++;
  cuttingCount = 0;
  drillTexts = [];
  if (gap !== null) endGap();
  if (current || waiting.length) note('stopped', {waiting: waiting.length, playing: current !== null});
  if (current) {
    current = null;
    player.pause();
  }
  waiting.forEach(url => URL.revokeObjectURL(url));
  waiting = [];
  drilled = new Set();
  askForTap(false);
  emit('stopped');
}

function element() {
  if (!player) {
    player = new Audio();
    for (const event of ['stalled', 'waiting', 'suspend', 'emptied']) {
      player.addEventListener(event, () => current && note(event, {ready: player.readyState, network: player.networkState}));
    }
  }
  return player;
}

/** Show (or remove) the request for a tap. It stays while the reply's text keeps arriving. */
function askForTap(needed) {
  pinStatus(needed ? 'Tap anywhere to hear the reply.' : '');
}

function playNext() {
  if (current || gap !== null || !waiting.length) return;
  const audio = element();
  const mine = current = {};
  audio.src = waiting[0];
  const phrase = drilled.has(waiting[0]);
  audio.defaultPlaybackRate = audio.playbackRate = phrase ? DRILL_RATE : opts.slow ? 0.8 : 1;
  audio.preservesPitch = true;
  const release = () => {
    current = null;
    audio.onended = audio.onerror = audio.onpause = null;
  };
  const done = () => {
    if (current !== mine) return;   // stopped meanwhile
    release();
    const url = waiting.shift();
    URL.revokeObjectURL(url);
    if (drilled.delete(url) && !lastPhrase()) {   // the learner's turn to say it
      const seconds = Number.isFinite(audio.duration) ? audio.duration : 2;
      pinStatus('Your turn: say it. Tap to go on.');
      gap = setTimeout(() => {
        endGap();
        playNext();
        emit('ended');
      }, pauseAfter(seconds, DRILL_RATE) * 1000);
      return;
    }
    playNext();
    emit('ended');
  };
  const refused = () => {   // keep the sentence for the next tap
    if (current !== mine) return;
    release();
    askForTap(true);
  };
  audio.onended = () => {
    note('ended', {seconds: round(audio.duration)});
    done();
  };
  audio.onerror = () => {
    note('error', {code: audio.error?.code, message: audio.error?.message});
    done();
  };
  audio.onpause = () => {   // paused by the phone: Stop clears current first, and the end sets audio.ended
    if (audio.ended) return;
    note('paused by the device', {at: round(audio.currentTime)});
    refused();
  };
  note('play', {waiting: waiting.length, ready: audio.readyState});
  audio.play().then(() => {
    note('playing', {seconds: round(audio.duration)});
    if (current === mine) askForTap(false);
  }).catch(e => {
    note('refused', {error: e.name, message: e.message});
    if (e.name === 'NotSupportedError') done();   // a file the browser can't play: skip it
    else refused();                               // refused, or interrupted before it began
  });
}

/** On every tap: play what's waiting, or renew the permission to play with a moment of silence. Either has to start
 * inside the tap itself, not after it. */
function onTap(e) {
  if (current) return;
  if (gap !== null) {   // ready before the pause ends
    note('tap ends the pause', {kind: e.type});
    endGap();
    playNext();
    emit('ended');
    return;
  }
  if (waiting.length) {
    note('tap plays what is waiting', {kind: e.type, waiting: waiting.length});
    askForTap(false);
    playNext();
    return;
  }
  const audio = element();
  audio.src = SILENCE;
  audio.play().then(() => note('tap renewed permission', {kind: e.type}))
    .catch(error => note('tap could not renew permission', {kind: e.type, error: error.name, message: error.message}));
}

const round = seconds => Number.isFinite(seconds) ? Math.round(seconds * 100) / 100 : null;

/** A WAV file of silence: 8 kHz, 16-bit, mono. Made here, so a tap never waits for a download. */
function silentWav(seconds) {
  const rate = 8000;
  const bytes = Math.round(rate * seconds) * 2;
  const view = new DataView(new ArrayBuffer(44 + bytes));
  const text = (at, s) => [...s].forEach((c, i) => view.setUint8(at + i, c.charCodeAt(0)));
  text(0, 'RIFF');
  view.setUint32(4, 36 + bytes, true);
  text(8, 'WAVEfmt ');
  view.setUint32(16, 16, true);         // size of the format section
  view.setUint16(20, 1, true);          // PCM
  view.setUint16(22, 1, true);          // mono
  view.setUint32(24, rate, true);
  view.setUint32(28, rate * 2, true);   // bytes per second
  view.setUint16(32, 2, true);          // bytes per sample
  view.setUint16(34, 16, true);         // bits per sample
  text(36, 'data');
  view.setUint32(40, bytes, true);
  return new Blob([view], {type: 'audio/wav'});
}

export function setupPlayer() {
  for (const event of ['pointerup', 'touchend', 'keydown']) addEventListener(event, onTap, {capture: true, passive: true});
  // Back on the page after switching apps: carry on if the phone allows it, or ask for a tap.
  document.addEventListener('visibilitychange', () => {
    note('page ' + document.visibilityState, {waiting: waiting.length, playing: current !== null});
    if (document.visibilityState === 'visible') playNext();
  });
}
