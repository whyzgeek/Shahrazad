// Where new messages and corrections go, and keeping the newest in view.
//
// The conversation and the corrections share one order: newest at the bottom (chat style) or at the top. The server's
// default comes from TUTOR_NEWEST in .env; the button in the header changes it for this browser.
// Both panes follow new content. Scrolling away to read pauses that pane; scrolling back to the newest end, or starting
// a new exchange, resumes it.
import {$, pref, setPref} from './util.js';

let newest = pref('shahrazad-newest', null) || document.documentElement.dataset.newest || 'bottom';
const following = new Map();   // pane -> whether it follows new content

/** Add a message or card to a pane, at its newest end. */
export function place(parent, node) {
  if (newest === 'top') parent.prepend(node);
  else parent.append(node);
}

function toNewest(pane) {
  pane.scrollTop = newest === 'top' ? 0 : pane.scrollHeight;
  pane._scrolledByPage = pane.scrollTop;
}

const atNewest = pane => newest === 'top'
  ? pane.scrollTop < 80
  : pane.scrollHeight - pane.scrollTop - pane.clientHeight < 80;

/** Both panes jump to their newest content and follow it again. */
export function followAll() {
  for (const pane of following.keys()) {
    following.set(pane, true);
    toNewest(pane);
  }
}

function follow(pane, list, onScroll) {
  following.set(pane, true);
  pane.addEventListener('scroll', () => {
    if (Math.abs(pane.scrollTop - pane._scrolledByPage) > 2) following.set(pane, atNewest(pane));   // the learner scrolled
    onScroll();
  }, {passive: true});
  // Heights also change without new content, for example when the Arabic font finishes loading.
  const resized = new ResizeObserver(() => {
    if (following.get(pane)) toNewest(pane);
  });
  new MutationObserver(changes => {
    for (const change of changes) {
      change.addedNodes.forEach(n => {
        if (n.nodeType === Node.ELEMENT_NODE && n.parentNode === list) resized.observe(n);
      });
    }
    if (following.get(pane)) toNewest(pane);
  }).observe(pane, {subtree: true, childList: true, characterData: true});
}

function showOrder() {
  $('order').textContent = newest === 'top' ? 'Newest first ↑' : 'Newest last ↓';
}

export function setupLayout(onScroll) {
  follow($('log'), $('log'), onScroll);
  follow($('notes'), $('notelist'), onScroll);
  $('order').onclick = () => {
    newest = newest === 'top' ? 'bottom' : 'top';
    setPref('shahrazad-newest', newest);
    for (const list of [$('log'), $('notelist')]) [...list.children].reverse().forEach(c => list.append(c));
    showOrder();
    followAll();
  };
  showOrder();
}
