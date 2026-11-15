// Just enough of a browser for the page's modules to run under Node's test runner, including a phone's rules for
// playing sound. Import this before any page module: they read globals such as `document` when they load.
//
// The phone, like iOS Safari and Chrome on Android with a strict policy, lets an audio element play only during a tap,
// or later if a tap has already started that element. It can also withdraw that permission (as phones do when the
// microphone opens or closes) and pause a sentence by itself (a call, a change of speaker).

export const phone = {
  strict: true,         // false: everything may play, like a desktop browser after any click
  tapping: false,       // inside a tap's event handlers now
  revoke() {            // take back the permission every element has
    for (const audio of phone.elements) audio.allowed = false;
  },
  fail: null,           // the error name the next play() fails with, such as 'AbortError'
  elements: [],
  played: [],           // the file each play() really started, in order
};

// Remember the file behind each object URL, so a test can tell which sentence played even after the page revokes it.
const files = new Map();
const createObjectURL = URL.createObjectURL;
URL.createObjectURL = blob => {
  const url = createObjectURL(blob);
  files.set(url, blob);
  return url;
};

/** What has played so far, as text: each sentence's bytes, with the page's moments of silence left out. */
export async function heard() {
  const blobs = phone.played.filter(file => file instanceof Blob);   // a plain URL is a file of silence
  const texts = await Promise.all(blobs.map(blob => blob.text()));
  return texts.filter(text => !text.startsWith('RIFF'));
}

class Node {
  constructor(tag = 'div') {
    this.tagName = tag.toUpperCase();
    this.children = [];
    this.attributes = {};
    this.dataset = {};
    this.textContent = '';
    this.hidden = false;
    this.disabled = false;
    this.className = '';
    this.style = {setProperty(name, value) { this[name] = String(value); }};
    const classes = new Set();
    this.classList = {
      add: c => classes.add(c), remove: c => classes.delete(c), contains: c => classes.has(c),
      toggle: (c, on = !classes.has(c)) => (on ? classes.add(c) : classes.delete(c), on),
    };
  }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return this.attributes[name] ?? null; }
  append(...nodes) { this.children.push(...nodes); }
  addEventListener() {}
}

const elements = {};
const listeners = {};
const documentListeners = {};

globalThis.document = {
  documentElement: new Node('html'),
  body: new Node('body'),
  visibilityState: 'visible',
  getElementById: id => elements[id] || (elements[id] = Object.assign(new Node(), {id})),
  createElement: tag => new Node(tag),
  addEventListener: (type, fn) => (documentListeners[type] ||= []).push(fn),
};
globalThis.addEventListener = (type, fn) => (listeners[type] ||= []).push(fn);
globalThis.location = {search: '', protocol: 'https:', host: 'tutor.test', href: ''};
globalThis.matchMedia = query => ({matches: query === '(pointer:coarse)' && phone.touch === true});
const storage = new Map();
globalThis.localStorage = {
  getItem: k => storage.get(k) ?? null,
  setItem: (k, v) => storage.set(k, String(v)),
  clear: () => storage.clear(),
};

/** The text under the talk button. */
export const statusText = () => document.getElementById('st').textContent;

/** A tap on the page, as the browser delivers it: its handlers run while the tap is in progress. */
export function tap() {
  phone.tapping = true;
  try {
    for (const type of ['pointerup', 'touchend']) (listeners[type] || []).forEach(fn => fn({type}));
  } finally {
    phone.tapping = false;
  }
}

/** The phone shows the page again after another app. */
export function showPage() {
  (documentListeners.visibilitychange || []).forEach(fn => fn());
}

/** Let promises (play() and its handlers) settle. */
export const settle = () => new Promise(resolve => setTimeout(resolve, 0));

class FakeAudio {
  constructor() {
    this.src = '';
    this.paused = true;
    this.ended = false;
    this.allowed = false;
    this.playbackRate = this.defaultPlaybackRate = 1;
    this.onended = this.onerror = this.onpause = null;
    this.listeners = {};
    phone.elements.push(this);
  }

  addEventListener(type, fn) {
    (this.listeners[type] ||= []).push(fn);
  }

  play() {
    if (phone.fail) {
      const error = new Error('play() failed');
      error.name = phone.fail;
      phone.fail = null;
      return Promise.reject(error);
    }
    if (phone.strict && !phone.tapping && !this.allowed) {
      const error = new Error('play() needs a tap');
      error.name = 'NotAllowedError';
      return Promise.reject(error);
    }
    if (phone.tapping) this.allowed = true;
    this.paused = this.ended = false;
    phone.played.push(files.get(this.src) ?? this.src);
    return Promise.resolve();
  }

  pause() {
    if (this.paused) return;
    this.paused = true;
    this.onpause?.();
  }

  /** The sentence reaches its end. As in browsers, 'pause' fires first, with `ended` already set. */
  finish() {
    this.ended = true;
    this.paused = true;
    this.onpause?.();
    this.onended?.();
  }

  /** The phone pauses it by itself. */
  interrupt() {
    this.pause();
  }
}
globalThis.Audio = FakeAudio;

/** The element playing the tutor's voice. */
export const voice = () => phone.elements[0];

/** A new phone for each test: no elements, nothing played, no handlers left from the previous test's modules. */
export function newPhone({strict = true} = {}) {
  phone.strict = strict;
  phone.fail = null;
  phone.elements.length = phone.played.length = 0;
  for (const table of [listeners, documentListeners]) for (const type in table) delete table[type];
  document.getElementById('st').textContent = '';
}

let fresh = 0;
/** A page module loaded anew, with its own state (the modules it imports stay shared). */
export const freshImport = path => import(new URL(`../../web/js/${path}?fresh=${++fresh}`, import.meta.url));
