// The conversation pane. Each exchange ("turn") holds what the learner said, any article or video it opened, and the
// tutor's reply. It gets its number once the server has saved it.
import {send} from './connection.js';
import {addCorrection, clearCorrections, markAllSeen, turnNumbered} from './corrections.js';
import {followAll, place} from './layout.js';
import {opts} from './options.js';
import {drillComplete, isSpeaking, onPlayback, setDrill, setMuted, stopAudio} from './player.js';
import {$, ARABIC_LETTER, el, fetchJSON, flash, VOWEL_MARKS} from './util.js';

const log = $('log');
const turns = {};    // saved turn id -> {node, n}
let turn = null;     // the exchange being written now
let learner = null;  // what the learner says in it
let tutor = null;    // the tutor's reply in it
let startTalking = () => {};

export const turnElement = id => turns[id]?.node;
export const turnNumber = id => turns[id]?.n;

// ---------------------------------------------------------------- welcome
function hideWelcome() {
  $('welcome')?.remove();
}

function showWelcome() {
  if (log.querySelector('.turn,.src') || $('welcome')) return;
  const welcome = el('div');
  welcome.id = 'welcome';
  welcome.innerHTML = '<img src="assets/logo.png" alt=""><p>Practise speaking Modern Standard Arabic. ' +
    'Talk with the button below, or type, or start with one of these:</p><div class="starts"></div>';
  const starts = [
    ['Just talk', 'The tutor greets you and asks about your day', () => startTalking('مرحباً! أريد أن أتدرب على الكلام.')],
    ["Today's news from Al Jazeera", 'Pick a story and discuss it', () => startTalking('ما آخر الأخبار في الجزيرة؟')],
    ['Discuss a YouTube video', 'Paste a link to a video with Arabic captions', () => {
      const input = $('txt');
      input.placeholder = 'Paste a YouTube link with Arabic captions, then press Send';
      input.focus();
    }],
  ];
  for (const [title, detail, action] of starts) {
    const button = el('button', null, title);
    button.append(el('small', null, detail));
    button.onclick = action;
    welcome.querySelector('.starts').append(button);
  }
  log.append(welcome);
}

// ---------------------------------------------------------------- turns and messages
function newTurn() {
  hideWelcome();
  turn = el('section', 'turn');
  turn.append(el('div', 'num'));
  place(log, turn);
  followAll();
  return turn;
}

function message(kind, who) {
  const node = el('div', 'm ' + kind);
  const body = el('div', 'ar');
  body.dir = 'auto';
  node.append(el('div', 'who', who), body);
  (turn || newTurn()).append(node);
  return node;
}

const setText = (node, text) => {
  node.querySelector('.ar').textContent = text;
};

function tutorMessage(plain, vowelled = '', covered = 0) {
  const node = message('bot', 'Tutor');
  node._plain = plain;        // the reply as written
  node._vowelled = vowelled;  // the sentences spoken so far, with vowel marks
  node._covered = covered;    // how much of the written reply those replace
  return node;
}

/** One Arabic line: the vowelled sentences as they are spoken, then the rest as it is still being written. Every
 *  Arabic word is its own span, so it can be tapped for its meaning. */
function renderTutor(node) {
  let text = node._vowelled ? node._vowelled + ' ' + node._plain.slice(node._covered).trim() : node._plain;
  if (!opts.marks) text = text.replace(VOWEL_MARKS, '');
  const body = node.querySelector('.ar');
  body.textContent = '';
  for (const piece of text.trim().split(/(\s+)/)) {
    if (ARABIC_LETTER.test(piece)) body.append(el('span', 'w', piece));
    else if (piece) body.append(piece);
  }
}

function numberTurn(node, id, n) {
  node.id = 'turn-' + id;
  node.querySelector('.num').textContent = '#' + n;
  turns[id] = {node, n};
  turnNumbered(id, n);
}

/** Scroll to a turn, or to one underlined mistake in it, and outline it briefly. */
export function jump(id, errorId) {
  const node = turnElement(id);
  if (!node) return;
  const mark = errorId && node.querySelector(`mark.err[data-err="${errorId}"]`);
  (mark || node).scrollIntoView({block: 'center', behavior: 'smooth'});
  flash(node);
  if (mark) flash(mark);
}

// ------------------------------------------------- under a finished reply: Replay, Repeat after me and Translate
let replaying = null;   // the Replay button of the reply being replayed
let replaySent = false; // the server has sent all of it

function endReplay() {
  setDrill(false);
  replaying?.classList.remove('on');
  replaying = null;
  replaySent = false;
}

onPlayback(event => {
  if (event === 'stopped' || (replaying && replaySent && !isSpeaking())) endReplay();
});

export function replayFinished() {
  replaySent = true;
  drillComplete();
  if (!isSpeaking()) endReplay();
}

function addActions(node, id) {
  if (node.querySelector('.acts')) return;
  const row = el('div', 'acts');
  const start = (button, drill) => {
    stopAudio();
    setMuted(false);
    setDrill(drill);
    replaying = button;
    replaySent = false;
    button.classList.add('on');
    send('replay', drill ? {turn: id, drill: true} : {turn: id});
  };
  const replay = el('button', 'replay', '▶ Replay');
  replay.onclick = () => start(replay, false);
  // Slowly, a few words at a time, with a pause after each for the learner to say them.
  const repeat = el('button', 'repeat', '🗣 Repeat after me');
  repeat.onclick = () => start(repeat, true);
  const translate = el('button', 'translate', 'Translate');
  let english = null;
  translate.onclick = async () => {
    if (english) {
      english.remove();
      english = null;
      translate.textContent = 'Translate';
      return;
    }
    const shown = english = el('div', 'en', 'Translating…');
    node.append(shown);
    translate.textContent = 'Hide translation';
    try {
      const r = await fetchJSON('translate', {text: node._plain || node.querySelector('.ar').textContent});
      shown.textContent = r.english || 'Translation failed. Please try again.';
    } catch (e) {
      shown.textContent = 'Translation failed. Please try again.';
    }
  };
  row.append(replay, repeat, translate);
  node.append(row);
}

// ---------------------------------------------------------------- what the server tells the page
/** The learner starts a turn: by talking (no text yet) or by typing. */
export function startTurn(text = '') {
  tutor = null;
  newTurn();
  learner = message('me', 'You');
  if (text) setText(learner, text);
}

/** The live caption while the learner speaks. */
export function heard(text) {
  if (learner) setText(learner, text);
}

/** What the learner said, in full. Nothing heard: the empty turn goes away. */
export function heardFinal(text) {
  if (learner) setText(learner, text || '…');
  if (!text && turn && !turn.id) {
    turn.remove();
    turn = learner = null;
    showWelcome();
  }
}

/** The tutor's reply so far, as written. */
export function tutorWrites(text) {
  if (!tutor) tutor = tutorMessage('');
  tutor._plain = text;
  renderTutor(tutor);
}

/** The reply's sentences spoken so far, with vowel marks. */
export function tutorVowels(vowelled, covered) {
  if (!tutor) return;
  tutor._vowelled = vowelled;
  tutor._covered = covered;
  renderTutor(tutor);
}

/** The server saved this turn as number n. */
export function turnSaved(id, n) {
  if (tutor) addActions(tutor, id);
  if (turn) numberTurn(turn, id, n);
}

/** A card for an article, a video, or an option offered to the learner. */
export function sourceCard(kind, title, url) {
  hideWelcome();
  const card = el('div', 'src');
  card.append(el('b', null, kind + ': '));
  if (/^https?:\/\//.test(url)) {
    const link = el('a', null, title);
    link.href = url;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    card.append(link);
  } else {
    card.append(title);
  }
  if (turn) turn.append(card);
  else place(log, card);
}

/** With debug on: how long the reply's first audio took. */
export function showTiming(seconds) {
  if (tutor) tutor.append(el('div', 'time', `First audio ${seconds ?? '–'} s after you stopped`));
}

/** Show a whole saved conversation: its subject, its turns and their corrections. */
export function loadConversation(m) {
  turn = learner = tutor = null;
  for (const id in turns) delete turns[id];
  log.textContent = '';
  clearCorrections();
  if (m.subject) sourceCard(m.subject.kind === 'video' ? 'Video' : 'Article', m.subject.title, m.subject.url);
  m.turns.forEach((t, i) => {
    newTurn();
    setText(message('me', 'You'), t.said);
    const reply = tutorMessage(t.reply, t.spoken || '', t.spoken ? t.reply.length : 0);
    renderTutor(reply);
    if (t.id) {
      addActions(reply, t.id);
      numberTurn(turn, t.id, i + 1);
    }
  });
  turn = null;
  m.errors.forEach(addCorrection);
  markAllSeen();
  showWelcome();
  followAll();
}

export function setupConversation({onStart}) {
  startTalking = onStart;
}

/** Vowel marks were switched on or off. */
export function rerender() {
  document.querySelectorAll('.m.bot').forEach(renderTutor);
}
