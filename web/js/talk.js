// Talking and typing to the tutor: the talk button (hold, or tap to start and tap to send), the space bar, the Stop
// button, and the typed message box. The talk button also shows what the tutor is doing.
import {send, sendAudio} from './connection.js';
import {startTurn} from './conversation.js';
import {cardsOpen, closeCards} from './corrections.js';
import {glossOpen, hideGloss} from './gloss.js';
import {closeMic, openMic} from './mic.js';
import {onOptionChange, opts, touch} from './options.js';
import {isSpeaking, setMuted, stopAudio} from './player.js';
import {$, setStatus} from './util.js';

const button = $('talk');
const stopButton = $('stop');
const MAX_TURN_MS = 300000;        // a turn ends by itself after 5 minutes
const THINKING_TIMEOUT_MS = 120000; // never stuck on "Thinking…"
let talking = false;
let busy = false;                  // waiting for the tutor's reply
let busySince = 0;
let turnLimit = null;

export function setBusy(value) {
  busy = value;
  busySince = Date.now();
  updateState();
}

function idleLabel() {
  if (opts.tap) return touch ? 'Tap to talk' : 'Tap to talk (or press the space bar)';
  return touch ? 'Hold to talk' : 'Hold to talk (or hold the space bar)';
}

const LABELS = {
  listen: () => opts.tap ? 'Listening… tap to send' : 'Listening… release when done',
  think: () => 'Thinking…',
  speak: () => 'Speaking…',
  idle: idleLabel,
};

/** Show on the talk button what is happening, with Stop while the tutor thinks or speaks. */
export function updateState() {
  if (button.disabled) return;
  if (busy && Date.now() - busySince > THINKING_TIMEOUT_MS) busy = false;
  const state = talking ? 'listen' : isSpeaking() ? 'speak' : busy ? 'think' : 'idle';
  button.classList.toggle('on', state === 'listen');
  const label = LABELS[state]();
  if (button.textContent !== label) button.textContent = label;
  stopButton.hidden = !(state === 'think' || state === 'speak');
}

export function setConnected(connected) {
  button.disabled = !connected;
  if (connected) {
    setStatus('');
    updateState();
  } else {
    button.textContent = 'Reconnecting…';
    stopButton.hidden = true;
    busy = false;
  }
}

/** Stop the tutor: its voice, and the reply it's writing. */
function stopTutor() {
  setMuted(true);
  stopAudio();
  setBusy(false);
  send('cancel');
}

async function startTalking() {
  if (talking || button.disabled) return;
  talking = true;
  hideGloss();
  try {
    await openMic(pcm => {
      if (talking) sendAudio(pcm);
    });
  } catch (e) {
    talking = false;
    closeMic();
    setStatus('Microphone unavailable. Open this page at http://localhost:8791 through the SSH tunnel and allow the mic.');
    return;
  }
  if (!talking) return;   // released during the permission prompt
  stopAudio();
  setMuted(false);
  setBusy(false);
  startTurn();
  setStatus('');
  send('start');
  turnLimit = setTimeout(stopTalking, MAX_TURN_MS);
  updateState();
}

function stopTalking() {
  if (!talking) return;
  talking = false;
  clearTimeout(turnLimit);
  setBusy(true);
  setTimeout(() => {   // the last chunk of audio is still on its way from the microphone
    send('stop');
    if (!talking) closeMic();
  }, 120);
}

/** Send a typed message (or a starter's text) as the learner's turn. */
export function sendText(text) {
  stopAudio();
  setMuted(false);
  hideGloss();
  startTurn(text);
  setBusy(true);
  send('text', {text});
}

const typing = () => document.activeElement === $('txt');

function onKeyDown(e) {
  if (e.code === 'Escape') {
    if (glossOpen()) hideGloss();
    else if (cardsOpen()) closeCards();
    else if (busy || isSpeaking()) stopTutor();
    return;
  }
  if (e.code === 'Space' && !e.repeat && !typing()) {
    e.preventDefault();
    if (opts.tap && talking) stopTalking();
    else startTalking();
  }
}

function onKeyUp(e) {
  if (e.code === 'Space' && !typing()) {
    e.preventDefault();
    if (!opts.tap) stopTalking();
  }
}

export function setupTalk() {
  button.onpointerdown = e => {
    e.preventDefault();
    if (opts.tap) {
      if (talking) stopTalking();
      else startTalking();
      return;
    }
    button.setPointerCapture(e.pointerId);
    startTalking();
  };
  button.onpointerup = () => {
    if (!opts.tap) stopTalking();
  };
  button.onpointercancel = button.onpointerup;
  stopButton.onclick = stopTutor;
  addEventListener('keydown', onKeyDown);
  addEventListener('keyup', onKeyUp);
  $('f').onsubmit = e => {
    e.preventDefault();
    const input = $('txt');
    const text = input.value.trim();
    if (!text) return;
    input.value = '';
    input.placeholder = 'Type here, or paste a YouTube link';
    sendText(text);
  };
  onOptionChange(updateState);
  setInterval(updateState, 250);
}
