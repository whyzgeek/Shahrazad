// A diary of how the tutor's voice plays on this device, sent to the server (data/playback.jsonl there), so a phone
// that won't play a reply shows why: each attempt, what the browser said, taps, the microphone, the page being hidden.
// It holds no speech or text, only these events.
import {send} from './connection.js';

const started = performance.now();
const waiting = [];   // events from before the connection opened

/** Write one event, such as note('refused', {error: 'NotAllowedError'}). */
export function note(event, details = {}) {
  const entry = {event, ms: Math.round(performance.now() - started), ...state(), ...details};
  if (!send('playback', entry)) waiting.push(entry);
}

/** Once connected: what this device is, then anything written before. */
export function connected() {
  send('playback', {event: 'page', ms: Math.round(performance.now() - started), device: navigator.userAgent, ...state()});
  while (waiting.length) send('playback', waiting.shift());
}

function state() {
  const activation = navigator.userActivation;
  return {
    visible: document.visibilityState,
    session: navigator.audioSession?.type,
    tapActive: activation ? activation.isActive : undefined,
  };
}
