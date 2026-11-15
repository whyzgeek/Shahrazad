// The choices under the talk button, remembered by each browser: tap or hold to talk, a slower voice, vowel marks,
// and the text size.
import {$, pref, setPref} from './util.js';

/** A phone or tablet. Holding a button while speaking is awkward there, so touch screens tap to talk by default. */
export const touch = matchMedia('(pointer:coarse)').matches;

export const opts = {
  tap: pref('shahrazad-tap', touch ? '1' : '0') === '1',
  slow: pref('shahrazad-slow', '0') === '1',
  marks: pref('shahrazad-marks', '1') === '1',
};

// The text size of what is read: the conversation, the correction cards, the panels and word meanings (style.css:
// --text-scale). The buttons stay as they are.
export const TEXT_SIZES = [0.85, 1, 1.15, 1.3, 1.5];
const savedSize = Number(pref('shahrazad-size', '1'));
export let textSize = TEXT_SIZES.includes(savedSize) ? savedSize : 1;

const listeners = [];

/** Call fn(name) whenever an option changes. */
export const onOptionChange = fn => listeners.push(fn);

function show() {
  for (const name in opts) $('o-' + name).setAttribute('aria-pressed', opts[name]);
  document.documentElement.style.setProperty('--text-scale', textSize);
  $('o-size').textContent = Math.round(textSize * 100) + '%';
  $('o-smaller').disabled = textSize === TEXT_SIZES[0];
  $('o-larger').disabled = textSize === TEXT_SIZES.at(-1);
}

/** One step smaller (-1) or larger (+1). */
function resize(step) {
  const next = TEXT_SIZES[TEXT_SIZES.indexOf(textSize) + step];
  if (next === undefined) return;
  textSize = next;
  setPref('shahrazad-size', String(next));
  show();
  listeners.forEach(fn => fn('size'));
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
  $('o-smaller').onclick = () => resize(-1);
  $('o-larger').onclick = () => resize(1);
  show();
}
