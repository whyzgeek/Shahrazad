// The sidebar: earlier conversations grouped by day, with rename and delete, and a new conversation.
import {send} from './connection.js';
import {closeCards} from './corrections.js';
import {closePanel} from './panels.js';
import {$, el, plural} from './util.js';

const DAY = 864e5;

function dayLabel(seconds) {
  const ms = seconds * 1000;
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  if (ms >= today) return 'Today';
  if (ms >= today - DAY) return 'Yesterday';
  if (ms >= today - 6 * DAY) return 'This week';
  return new Date(ms).toLocaleDateString(undefined, {month: 'long', year: 'numeric'});
}

const closeSidebar = () => document.body.classList.remove('nav');

function row(session, current) {
  const item = el('div', 'sr' + (session.id === current ? ' cur' : ''));
  const open = el('button', 'si');
  const title = el('span', 't1', session.title);
  title.dir = 'auto';
  open.append(title, el('span', 't2', plural(session.turns, 'turn')));
  open.title = session.title;
  open.onclick = () => {
    closeSidebar();
    closePanel();
    if (session.id !== current) send('switch', {id: session.id});
  };
  const rename = el('button', null, '✎');
  rename.title = 'Rename';
  rename.setAttribute('aria-label', 'Rename ' + session.title);
  rename.onclick = () => {
    const name = prompt('Rename this conversation', session.title)?.trim();
    if (name && name !== session.title) send('rename', {id: session.id, title: name});
  };
  const remove = el('button', null, '✕');
  remove.title = 'Delete';
  remove.setAttribute('aria-label', 'Delete ' + session.title);
  remove.onclick = () => {
    if (confirm(`Delete “${session.title}” and its corrections? What you have practised stays in your progress.`)) {
      send('delete', {id: session.id});
    }
  };
  const ops = el('div', 'ops');
  ops.append(rename, remove);
  item.append(open, ops);
  return item;
}

export function renderSessions({sessions, current}) {
  const list = $('slist');
  list.textContent = '';
  let lastDay = '';
  for (const session of sessions) {
    const day = dayLabel(session.updated || 0);
    if (day !== lastDay) {
      list.append(el('div', 'day', day));
      lastDay = day;
    }
    list.append(row(session, current));
    if (session.id === current) $('ctitle').textContent = session.title;
  }
}

export function setupSessions() {
  $('newc').onclick = () => {
    closeSidebar();
    closePanel();
    send('reset');
  };
  $('menu').onclick = () => document.body.classList.toggle('nav');
  $('shade').onclick = () => {
    closeSidebar();
    closeCards();
  };
  $('logout').hidden = document.documentElement.dataset.login !== '1';
}
