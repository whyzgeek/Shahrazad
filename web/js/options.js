// The choices under the talk button, remembered by each browser: tap or hold to talk, a slower voice, vowel marks.
import {$, pref, setPref} from './util.js';

/** A phone or tablet. Holding a button while speaking is awkward there, so touch screens tap to talk by default. */
export const touch = matchMedia('(pointer:coarse)').matches;

export const opts = {
  tap: pref('shahrazad-tap', touch ? '1' : '0') === '1',
  slow: pref('shahrazad-slow', '0') === '1',
  marks: pref('shahrazad-marks', '1') === '1',
};

const listeners = [];

/** Call fn(name) whenever an option changes. */
export const onOptionChange = fn => listeners.push(fn);

function show() {
  for (const name in opts) $('o-' + name).setAttribute('aria-pressed', opts[name]);
}

export function setupOptions() {
  for (const name in opts) {
    $('o-' + name).onclick = () => {
      opts[name] = !opts[name];
      setPref('shahrazad-' + name, opts[name] ? '1' : '0');
      show();
      listeners.forEach(fn => fn(name));
    };
  }
  show();
}
