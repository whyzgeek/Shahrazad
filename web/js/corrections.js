// Corrections: each one is underlined where the learner said it and has a card in the corrections pane. On a phone the
// pane opens as a panel from the bottom, from the header button or by tapping an underlined mistake.
import {send} from './connection.js';
import {jump, turnNumber, turnElement} from './conversation.js';
import {place} from './layout.js';
import {$, el, fetchJSON, flash, plural, VOWEL_MARKS} from './util.js';

const byTurn = {};   // turn id -> its corrections
let seen = 0;        // how many cards the learner has seen, so the header button can show there are new ones
const narrow = matchMedia('(max-width:800px)');

// ---------------------------------------------------------------- underlining in what the learner said
// The match ignores vowel marks, spacing and the usual spelling variants (أ إ آ ا, ى ي, ة ه), since the card's text and
// the transcript can differ slightly.
const VARIANTS = {'ا': '[اأإآ]', 'أ': '[اأإآ]', 'إ': '[اأإآ]', 'آ': '[اأإآ]', 'ى': '[ىي]', 'ي': '[ىي]', 'ة': '[ةه]', 'ه': '[ةه]'};
const PUNCTUATION = /[ـ.,،؟?!:؛"«»]/g;

function pattern(words) {
  const letters = [...words.replace(VOWEL_MARKS, '').replace(PUNCTUATION, '').replace(/\s+/g, ' ').trim()];
  if (!letters.length) return null;
  const parts = letters.map(c => {
    if (c === ' ') return '[\\s.,،؟?!:؛"«»]+';
    return VARIANTS[c] || c.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  });
  return new RegExp(parts.join('[ً-ْٰـ]*'));   // vowel marks or a tatweel may sit between any two letters
}

/** Underline each correction in the learner's message for this turn. Ones not found word for word get a link instead. */
export function markTurn(turnId) {
  const said = turnElement(turnId)?.querySelector('.m.me');
  if (!said) return;
  const body = said.querySelector('.ar');
  const text = body.textContent;
  const spans = [];
  const missed = [];
  said.querySelector('.who .errs')?.remove();
  for (const e of byTurn[turnId] || []) {
    const m = pattern(e.wrong)?.exec(text);
    const overlaps = m && spans.some(s => m.index < s.end && m.index + m[0].length > s.start);
    if (m && !overlaps) spans.push({start: m.index, end: m.index + m[0].length, e});
    else missed.push(e);
  }
  spans.sort((a, b) => a.start - b.start);
  body.textContent = '';
  let at = 0;
  for (const s of spans) {
    body.append(text.slice(at, s.start));
    const mark = el('mark', 'err', text.slice(s.start, s.end));
    mark.dataset.err = s.e.id;
    mark.title = s.e.right + ' (show the correction)';
    mark.onclick = () => showCorrection(s.e.id);
    body.append(mark);
    at = s.end;
  }
  body.append(text.slice(at));
  if (missed.length) {   // found by the check, but not word for word in the transcript
    const link = el('a', 'errs', ' · ' + plural(missed.length, 'correction'));
    link.href = '#';
    link.onclick = ev => {
      ev.preventDefault();
      showCorrection(missed[0].id);
    };
    said.querySelector('.who').append(link);
  }
}

// ---------------------------------------------------------------- the cards
/** A button that shows the lesson for a rule above `before` inside `card`, and hides it again. */
export function lessonButton(key, card, before) {
  const button = el('button', null, 'Explain this');
  let box = null;
  button.onclick = async () => {
    if (box) {
      box.remove();
      box = null;
      button.textContent = 'Explain this';
      return;
    }
    const lesson = await fetchJSON('lesson/' + encodeURIComponent(key));
    box = el('div', 'lesson');
    const rule = el('p', null, lesson.rule);
    rule.dir = 'auto';
    box.append(rule);
    if (lesson.examples) {
      const list = el('ul');
      list.dir = 'rtl';
      lesson.examples.forEach(t => list.append(el('li', null, t)));
      box.append(list);
    }
    if (lesson.trap) box.append(el('p', 'trap', lesson.trap));
    card.insertBefore(box, before());
    button.textContent = 'Hide';
  };
  return button;
}

/** The wrong words struck through, then the right ones. */
export function fixLine(wrong, right) {
  const line = el('div', 'fix');
  line.dir = 'rtl';
  line.append(el('s', null, wrong), ' ← ', el('b', null, right));
  return line;
}

export function addCorrection(e) {
  const card = el('div', 'note');
  card.dataset.turn = e.turn ?? '';
  card.dataset.id = e.id;
  if (e.turn != null) {
    (byTurn[e.turn] = byTurn[e.turn] || []).push(e);
    markTurn(e.turn);
  }
  const number = turnNumber(e.turn);
  const where = el('a', 'tn', number ? '#' + number : '');
  where.href = '#';
  where.title = 'Show where you said it';
  where.onclick = ev => {
    ev.preventDefault();
    closeCards();
    jump(e.turn, e.id);
  };
  const reminder = el('div', null, e.reminder);
  reminder.dir = 'auto';
  const actions = el('div', 'act');
  const notSaid = el('button', null, "That's not what I said");
  notSaid.onclick = () => {
    send('dismiss', {id: e.id});
    card.remove();
    byTurn[e.turn] = (byTurn[e.turn] || []).filter(x => x.id !== e.id);
    markTurn(e.turn);
    countCards();
  };
  actions.append(lessonButton(e.key, card, () => actions), notSaid);
  card.append(where, fixLine(e.wrong, e.right), el('div', 'c', e.concept), reminder, actions);
  place($('notelist'), card);
  countCards();
}

/** A turn got its number: show it on its cards, and underline its corrections. */
export function turnNumbered(turnId, n) {
  document.querySelectorAll(`.note[data-turn="${turnId}"] .tn`).forEach(x => x.textContent = '#' + n);
  markTurn(turnId);
}

export function clearCorrections() {
  for (const id in byTurn) delete byTurn[id];
  $('notelist').textContent = '';
  countCards();
}

/** The cards of a conversation being opened count as seen. */
export function markAllSeen() {
  seen = $('notelist').children.length;
  countCards();
}

export function showCorrection(id) {
  const card = document.querySelector(`.note[data-id="${id}"]`);
  if (!card) return;
  openCards();
  card.scrollIntoView({block: 'nearest', behavior: 'smooth'});
  flash(card);
}

// ---------------------------------------------------------------- the pane on a phone
export const cardsOpen = () => document.body.classList.contains('cards');

function openCards() {
  if (!narrow.matches) return;
  document.body.classList.add('cards');
  seen = $('notelist').children.length;
  countCards();
}

export function closeCards() {
  document.body.classList.remove('cards');
}

function countCards() {
  const n = $('notelist').children.length;
  const button = $('cardsb');
  $('notes').hidden = !n;
  button.hidden = !n;
  if (!n) {
    closeCards();
    seen = 0;
  }
  if (cardsOpen()) seen = n;
  button.textContent = 'Cards ' + n;
  button.title = plural(n, 'correction');
  button.classList.toggle('new', n > seen);
}

export function setupCorrections() {
  $('cardsb').onclick = openCards;
  $('nclose').onclick = closeCards;
}
