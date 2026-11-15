// The tutor's voice: one audio element plays the sentences in order as they arrive.
//
// Phones treat an audio element like a music player: at media volume, and once a tap has started it, it may go on
// playing new sentences by itself. (Web Audio was paused by phones whenever the microphone opened or closed, so replies
// needed Replay.) Until a tap has unlocked it, every tap tries again with a moment of silence; a sentence the phone
// still refuses waits for the next tap.
import {opts} from './options.js';
import {setStatus} from './util.js';

const SILENCE = 'web/silence.wav';   // 50 ms

let player = null;
let unlocked = false;
let current = null;      // the sentence playing now
let waiting = [];        // object URLs of the sentences still to play
let muted = false;       // after Stop, audio still on its way is dropped
let askedForTap = false;
const listeners = [];

/** Call fn('ended') after each sentence, and fn('stopped') when playback is stopped. */
export const onPlayback = fn => listeners.push(fn);
const emit = event => listeners.forEach(fn => fn(event));

export const isSpeaking = () => current !== null || waiting.length > 0;

/** Drop voice that is still arriving (after Stop), or accept it again (a new turn). */
export function setMuted(value) {
  muted = value;
}

/** Queue one sentence of the tutor's voice (WAV or MP3 bytes). */
export function play(bytes) {
  if (muted) return;
  waiting.push(URL.createObjectURL(new Blob([bytes])));
  playNext();
}

export function stopAudio() {
  if (current) {
    current = null;
    player.pause();
  }
  waiting.forEach(url => URL.revokeObjectURL(url));
  waiting = [];
  emit('stopped');
}

function playNext() {
  if (current || !waiting.length) return;
  const url = waiting[0];
  const audio = player || (player = new Audio());
  const mine = current = {};
  audio.src = url;
  audio.defaultPlaybackRate = audio.playbackRate = opts.slow ? 0.8 : 1;
  audio.preservesPitch = true;
  const done = () => {
    if (current !== mine) return;   // stopped meanwhile
    current = null;
    audio.onended = audio.onerror = null;
    URL.revokeObjectURL(waiting.shift());
    playNext();
    emit('ended');
  };
  audio.onended = done;
  audio.onerror = done;
  audio.play().then(() => {
    unlocked = true;
  }).catch(e => {
    if (current !== mine) return;
    if (e.name === 'NotAllowedError') {   // the phone wants a tap first: keep the sentence for then
      current = null;
      askedForTap = true;
      setStatus('Tap anywhere to hear the reply.');
    } else {
      done();
    }
  });
}

function unlock() {
  if (!player) player = new Audio();
  if (!unlocked && !current) {
    player.src = SILENCE;
    player.play().then(() => {
      unlocked = true;
    }).catch(() => {});
  }
  if (askedForTap) {
    askedForTap = false;
    setStatus('');
  }
  if (!current && waiting.length) setTimeout(playNext, 0);
}

export function setupPlayer() {
  for (const event of ['pointerup', 'touchend', 'keydown']) addEventListener(event, unlock, {capture: true, passive: true});
}
