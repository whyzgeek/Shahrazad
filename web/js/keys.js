// Moving around the page with arrow keys and Enter: a keyboard, or the D-pad of a remote control on an Android phone
// or TV (its centre button arrives as Enter). A remote has no space bar, so the talk button is reachable too.
//
//   Up and Down    the tutor's replies, in the order shown, and the talk button below them as the last stop
//   Left and Right the buttons under the selected reply (Replay, Repeat after me, Translate)
//   Enter          presses the selected button; on the talk button, starts a turn and then sends it
//
// While typing in the message box, these keys are the box's; Esc leaves the box.
//
// Back (a phone's or remote's) doesn't reach a page as a key: it goes back in the page's history. So the page keeps
// one entry of its own on top, put there at a tap or key press (Chrome skips entries a page adds without one). Back
// then lands on the page itself: if the tutor is writing or speaking, that stops it; otherwise Back goes on and leaves.
import {cardsOpen} from './corrections.js';
import {stopTutor, toggleTalk, tutorActive} from './talk.js';
import {$} from './util.js';

let reply = null;    // the selected reply, or the talk button
let button = 0;      // which of its buttons

const talk = () => $('talk');
const typing = () => /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName || '');

/** The stops, top to bottom as shown: finished replies (they have buttons), then the talk button. */
function stops() {
  const replies = [...document.querySelectorAll('#log .m.bot')].filter(m => m.querySelector('.acts button'));
  replies.sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top);
  return [...replies, talk()];
}

/** The selected reply's buttons, left to right as shown. */
function buttons(node) {
  if (!node || node === talk()) return [];
  return [...node.querySelectorAll('.acts button')].sort((a, b) => a.getBoundingClientRect().left - b.getBoundingClientRect().left);
}

function show() {
  document.querySelectorAll('.kb-sel, .kb-btn').forEach(n => n.classList.remove('kb-sel', 'kb-btn'));
  if (!reply || !reply.isConnected) {
    reply = null;
    return;
  }
  reply.classList.add('kb-sel');
  const row = buttons(reply);
  button = Math.min(Math.max(button, 0), Math.max(row.length - 1, 0));
  row[button]?.classList.add('kb-btn');
  reply.scrollIntoView({block: 'nearest', behavior: 'smooth'});
}

/** The newest reply: where the first key press starts, as it's the one usually wanted. */
function newest(list) {
  const replies = [...document.querySelectorAll('#log .m.bot')].filter(m => m.querySelector('.acts button'));
  return replies.at(-1) || list.at(-1);
}

function move(step) {
  const list = stops();
  if (!reply || !list.includes(reply)) reply = newest(list);
  else reply = list[Math.min(Math.max(list.indexOf(reply) + step, 0), list.length - 1)];
  button = 0;
  show();
}

function side(step) {
  if (!reply || !reply.isConnected) return move(0);
  button += step;
  show();
}

function press() {
  if (!reply || !reply.isConnected) return move(0);
  if (reply === talk()) toggleTalk();
  else buttons(reply)[button]?.click();
  show();   // the buttons may have changed (Translate becomes Hide translation)
}

const ACTIONS = {ArrowUp: () => move(-1), ArrowDown: () => move(1), ArrowLeft: () => side(-1), ArrowRight: () => side(1),
                 Enter: press, NumpadEnter: press};

function onKey(e) {
  if (e.key === 'Escape' && typing()) document.activeElement.blur();   // back to moving around the page
  const action = ACTIONS[e.key] || ACTIONS[e.code];
  if (!action || typing() || cardsOpen() || e.altKey || e.ctrlKey || e.metaKey) return;
  if (e.repeat && (e.key === 'Enter' || e.code === 'NumpadEnter')) return;   // a held OK button presses once
  e.preventDefault();   // no scrolling or default button press on top of ours
  action();
}

let backTrap = false;   // the page's own history entry is on top

function armBack() {
  if (backTrap) return;
  history.pushState({shahrazad: 'back'}, '');
  backTrap = true;
}

function onBack() {
  if (!backTrap) return;   // our own history.back() below, on its way out
  backTrap = false;
  if (tutorActive()) stopTutor('Back');
  else history.back();
}

export function setupKeys() {
  addEventListener('keydown', onKey);
  for (const event of ['keydown', 'pointerdown']) addEventListener(event, armBack, {capture: true, passive: true});
  addEventListener('popstate', onBack);
}
