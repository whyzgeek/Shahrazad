// Tap a word in a reply for its meaning, shown in a small popover above it.
import {$, el, fetchJSON} from './util.js';

const pop = $('pop');
let word = null;   // the word whose meaning is shown

export const glossOpen = () => !pop.hidden;

export function hideGloss() {
  pop.hidden = true;
  word?.classList.remove('sel');
  word = null;
}

function position(target) {
  const r = target.getBoundingClientRect();
  const width = pop.offsetWidth;
  const height = pop.offsetHeight;
  pop.style.left = Math.max(8, Math.min(innerWidth - width - 8, r.left + r.width / 2 - width / 2)) + 'px';
  pop.style.top = (r.top - height - 8 > 8 ? r.top - height - 8 : r.bottom + 8) + 'px';   // above, or below near the top
}

async function show(target) {
  hideGloss();
  word = target;
  target.classList.add('sel');
  pop.textContent = '…';
  pop.hidden = false;
  position(target);
  const text = target.textContent.replace(/[^ء-يً-ْٰ]/g, '');
  try {
    const r = await fetchJSON('gloss', {word: text, sentence: target.closest('.m')._plain || ''});
    if (word !== target) return;   // another word was tapped meanwhile
    pop.textContent = '';
    if (r.meaning) {
      const base = el('div', 'base', r.base || text);
      base.dir = 'rtl';
      pop.append(base, el('div', null, r.meaning));
    } else {
      pop.textContent = 'No meaning found.';
    }
  } catch (e) {
    if (word === target) pop.textContent = 'Could not look this word up.';
  }
  position(target);
}

export function setupGloss() {
  $('log').addEventListener('click', e => {
    const target = e.target.closest('.m.bot .w');
    if (!target) return;
    e.stopPropagation();
    if (word === target) hideGloss();
    else show(target);
  });
  document.addEventListener('click', e => {
    if (glossOpen() && !pop.contains(e.target)) hideGloss();
  });
}
