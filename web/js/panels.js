// Full-page panels over the conversation (Progress and Status), and the banner shown when a part isn't answering.
import {send} from './connection.js';
import {jump, turnNumber} from './conversation.js';
import {closeCards, fixLine, lessonButton, showCorrection} from './corrections.js';
import {$, clock, el, fetchJSON, plural} from './util.js';

let refresh = null;   // the timer that keeps an open panel up to date

function openPanel(title) {
  document.body.classList.remove('nav');
  closeCards();
  clearInterval(refresh);
  $('ptitle').textContent = title;
  $('pbody').textContent = 'Loading…';
  $('prog').hidden = false;
  return $('pbody');
}

export function closePanel() {
  clearInterval(refresh);
  $('prog').hidden = true;
}

// ---------------------------------------------------------------- progress
// The level, what's being practised or learned, and every correction so far, from the learner record.
function chips(body, title, list, empty, detail) {
  body.append(el('h3', null, `${title} (${list.length})`));
  if (!list.length) {
    body.append(el('p', 'empty', empty));
    return;
  }
  const row = el('div', 'chips');
  for (const item of list) {
    const chip = el('span', 'chip' + (item.due ? ' due' : ''), item.title);
    const extra = detail(item);
    if (extra) chip.append(el('small', null, extra));
    row.append(chip);
  }
  body.append(row);
}

/** Open the conversation a correction came from, and show it there once it has loaded. */
function goToCorrection(c) {
  closePanel();
  send('switch', {id: c.session});
  const waiting = setInterval(() => {
    if (turnNumber(c.turn)) {
      clearInterval(waiting);
      jump(c.turn, c.id);
      showCorrection(c.id);
    }
  }, 200);
  setTimeout(() => clearInterval(waiting), 5000);
}

function correctionCard(c) {
  const card = el('div', 'note');
  const from = el('div', 'from');
  const link = el('a', null, c.title || 'Conversation');
  link.href = '#';
  link.onclick = ev => {
    ev.preventDefault();
    goToCorrection(c);
  };
  from.append('From ', link, ' · ' + new Date(c.at * 1000).toLocaleDateString());
  const actions = el('div', 'act');
  actions.append(lessonButton(c.key, card, () => actions));
  card.append(fixLine(c.wrong, c.right), el('div', 'c', c.concept), from, actions);
  return card;
}

async function openProgress() {
  const body = openPanel('Your progress');
  let p;
  try {
    p = await fetchJSON('progress');
  } catch (e) {
    body.textContent = 'Could not load your progress.';
    return;
  }
  body.textContent = '';
  const level = el('div', 'level');
  level.append(el('b', null, p.band), el('span', null,
    `Estimated from ${plural(p.turns, 'exchange')} in ${plural(p.sessions, 'conversation')}. The tutor adapts its language to this level.`));
  body.append(el('h3', null, 'Level'), level);
  chips(body, 'Practising', p.practising,
    'Nothing yet: rules you get wrong appear here, and the tutor brings them back in later conversations.',
    x => plural(x.times, 'mistake') + (x.due ? ' · due for practice' : ''));
  chips(body, 'Learned', p.learned, 'A rule counts as learned once you use it correctly on two different days.', () => '');
  const heading = el('h3', null, `All corrections (${p.cards.length})`);
  if (p.cards.length) {
    const csv = el('a', 'export', 'Export for Anki (CSV)');
    csv.href = 'cards.csv';
    csv.download = 'shahrazad-cards.csv';
    heading.append(csv);
  }
  const list = el('div');
  list.id = 'pcards';
  body.append(heading, list);
  if (!p.cards.length) list.append(el('p', 'empty', 'No corrections yet.'));
  p.cards.forEach(c => list.append(correctionCard(c)));
}

// ---------------------------------------------------------------- status
// What runs each part, whether it answers, when it stops by itself, and the cloud credit left.
const PARTS = {
  brain: ['Brain', 'Writes the replies, adds the vowels, finds your mistakes'],
  hearing: ['Hearing', 'Turns your speech into text'],
  voice: ['Voice', 'Reads the replies aloud'],
};

function lifetime(p) {
  if (!p.since) return '';
  return ` · running since ${clock(p.since)}` + (p.stops ? `, stops by itself at ${clock(p.stops)}` : '');
}

function statusCard({ok, title, name = '', what = '', where = '', state}) {
  const card = el('div', 'part' + (ok ? '' : ' down'));
  const heading = el('div', 'ph');
  heading.append(el('span', 'dot', ok ? '✓' : '✗'), el('b', null, title), el('span', 'pn', name));
  card.append(heading, el('div', 'pd', what), el('div', 'pd', where), el('div', 'ps', state));
  return card;
}

function partState(p) {
  if (p.ok) return 'Working';
  if (p.mode === 'cloud') return 'No OpenRouter key: add OPENROUTER_API_KEY to .env';
  return 'Not answering. On the server, run scripts/start.sh';
}

function creditCard(credit) {
  if (credit.error) return statusCard({ok: false, title: 'OpenRouter', what: credit.error, state: "Couldn't read the balance"});
  const enough = credit.left >= 1;
  return statusCard({
    ok: enough,
    title: 'OpenRouter',
    name: `$${credit.left.toFixed(2)} left of $${credit.total}`,
    what: 'Paid per use by the parts in the cloud',
    state: enough ? 'Enough for now' : 'Running low: add credit at openrouter.ai',
  });
}

async function showStatus() {
  const body = $('pbody');
  let s;
  try {
    s = await fetchJSON('status');
  } catch (e) {
    body.textContent = 'The tutor server is not answering. On the server, run scripts/start.sh.';
    return;
  }
  body.textContent = '';
  body.append(el('h3', null, 'Parts'));
  for (const p of s.parts) {
    const [title, what] = PARTS[p.kind] || [p.kind, ''];
    const where = p.mode === 'cloud' ? 'In the cloud, through OpenRouter' : `On this computer, GPU ${p.gpu}` + lifetime(p);
    body.append(statusCard({ok: p.ok, title, name: p.name, what, where, state: partState(p)}));
  }
  body.append(el('h3', null, 'Tutor'), statusCard({
    ok: true, title: 'Web app', name: 'Shahrazad', what: 'This page and the conversation',
    where: 'On this computer' + lifetime(s.app), state: 'Working',
  }));
  if (s.credit) body.append(el('h3', null, 'Cloud credit'), creditCard(s.credit));
  body.append(el('p', 'empty', `Checked at ${new Date().toLocaleTimeString()}. Updates every 5 seconds while open.`));
}

function openStatus() {
  openPanel('Status');
  showStatus();
  refresh = setInterval(() => {
    if (!$('prog').hidden) showStatus();
  }, 5000);
}

// ---------------------------------------------------------------- the banner
// When a part of the tutor isn't answering, a banner says so, instead of a page that seems frozen.
export async function checkHealth() {
  let health;
  try {
    health = await fetchJSON('health');
  } catch (e) {
    return;
  }
  const down = Object.values(health).filter(p => !p.ok);
  const banner = $('banner');
  banner.hidden = !down.length;
  if (!down.length) return;
  const local = down.filter(p => p.mode !== 'cloud').map(p => p.name);
  const cloud = down.filter(p => p.mode === 'cloud');
  const lines = [];
  if (local.length) {
    lines.push(`${local.join(', ')} ${local.length > 1 ? 'are' : 'is'} not responding, so replies may not come. On the server, run scripts/start.sh.`);
  }
  if (cloud.length) lines.push('No OpenRouter key is set for the cloud parts. Add OPENROUTER_API_KEY to .env.');
  lines.push('Tap for details.');
  banner.textContent = lines.join(' ');
}

export function setupPanels() {
  $('pclose').onclick = closePanel;
  $('progb').onclick = openProgress;
  $('statb').onclick = openStatus;
  $('banner').onclick = openStatus;
  checkHealth();
  setInterval(checkHealth, 20000);
}
