// Small helpers shared by every part of the page.

export const $ = id => document.getElementById(id);

export const ARABIC_LETTER = /[ء-ي]/;
export const VOWEL_MARKS = /[ً-ْٰ]/g;

// Debug details (such as reply timings) show when the server logs transcripts, or with ?debug in the address.
export const DEBUG = document.documentElement.dataset.debug === '1' || /[?&]debug\b/.test(location.search);

/** A new element, with an optional class and text. */
export function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

/** A per-browser setting. Storage can be unavailable (a private window), so it falls back to the default. */
export function pref(key, fallback) {
  try {
    return localStorage.getItem(key) ?? fallback;
  } catch (e) {
    return fallback;
  }
}

export function setPref(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch (e) {
    // Not remembered, but the page still works.
  }
}

/** JSON from the server: a GET, or a POST when there is a body. A 401 means the login has expired. */
export async function fetchJSON(path, body) {
  const init = body === undefined ? {} : {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body),
  };
  const response = await fetch(path, init);
  if (response.status === 401) {
    location.href = 'login';
    throw new Error('login required');
  }
  return response.json();
}

/** "1 turn", "3 turns". */
export const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;

/** A Unix time as a clock time, in the viewer's 12- or 24-hour format. */
export const clock = seconds => new Date(seconds * 1000).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});

let pinned = '';   // a message ordinary updates don't clear, such as a request to tap

/** The line of status text under the talk button. */
export function setStatus(text) {
  $('st').textContent = text || pinned;
}

/** Show a message until it's unpinned with pinStatus(''), which leaves alone any newer message shown since. */
export function pinStatus(text) {
  const was = pinned;
  pinned = text;
  if (text) $('st').textContent = text;
  else if (was && $('st').textContent === was) $('st').textContent = '';
}

/** Briefly outline an element, to show where something is. */
export function flash(node) {
  node.classList.add('flash');
  setTimeout(() => node.classList.remove('flash'), 1600);
}
