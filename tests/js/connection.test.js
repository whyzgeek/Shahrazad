// The WebSocket to the tutor (web/js/connection.js), the page's options (options.js) and small helpers (util.js).
import {phone} from './fake-browser.js';
import {test} from 'node:test';
import assert from 'node:assert/strict';

const sockets = [];
globalThis.WebSocket = class {
  static OPEN = 1;
  constructor(url) {
    this.url = url;
    this.readyState = 0;
    this.sent = [];
    sockets.push(this);
  }
  send(data) { this.sent.push(data); }
};

const timers = [];
const realSetTimeout = globalThis.setTimeout;

const {connect, send, sendAudio} = await import('../../web/js/connection.js');

test('events wait for the connection, then go as JSON; audio goes as it is', () => {
  const got = {events: [], audio: [], opened: 0, closed: 0};
  connect({
    onOpen: () => got.opened++, onClose: () => got.closed++,
    onEvent: e => got.events.push(e), onAudio: a => got.audio.push(a),
  });
  const socket = sockets.at(-1);
  assert.equal(socket.url, 'wss://tutor.test/ws');
  assert.equal(socket.binaryType, 'arraybuffer');
  send('text', {text: 'مرحبا'});
  assert.deepEqual(socket.sent, [], 'nothing is sent before the connection opens');
  socket.readyState = WebSocket.OPEN;
  socket.onopen();
  send('text', {text: 'مرحبا'});
  const pcm = new ArrayBuffer(4);
  sendAudio(pcm);
  assert.deepEqual(socket.sent, ['{"type":"text","text":"مرحبا"}', pcm]);
  socket.onmessage({data: '{"type":"turn","id":3}'});
  socket.onmessage({data: pcm});
  assert.deepEqual(got.events, [{type: 'turn', id: 3}]);
  assert.deepEqual(got.audio, [pcm]);
  assert.equal(got.opened, 1);
});

test('a dropped connection is reported and tried again after 1.5 s', () => {
  globalThis.setTimeout = (fn, ms) => timers.push({fn, ms});
  try {
    let closed = 0;
    const handlers = {onOpen() {}, onClose: () => closed++, onEvent() {}, onAudio() {}};
    connect(handlers);
    const count = sockets.length;
    sockets.at(-1).onclose();
    assert.equal(closed, 1);
    assert.equal(timers.at(-1).ms, 1500);
    timers.at(-1).fn();
    assert.equal(sockets.length, count + 1, 'a new connection');
  } finally {
    globalThis.setTimeout = realSetTimeout;
  }
});

test('options are remembered per browser, and tap-to-talk is the default on touch screens', async () => {
  localStorage.clear();
  phone.touch = true;
  const touchOptions = await import('../../web/js/options.js?touch');
  assert.equal(touchOptions.touch, true);
  assert.equal(touchOptions.opts.tap, true);
  assert.equal(touchOptions.opts.marks, true);
  assert.equal(touchOptions.opts.slow, false);

  phone.touch = false;
  const changed = [];
  const options = await import('../../web/js/options.js?desktop');
  assert.equal(options.opts.tap, false);
  options.onOptionChange(name => changed.push(name));
  options.setupOptions();
  const button = document.getElementById('o-slow');
  assert.equal(button.getAttribute('aria-pressed'), 'false');
  button.onclick();
  assert.equal(options.opts.slow, true);
  assert.equal(button.getAttribute('aria-pressed'), 'true');
  assert.equal(localStorage.getItem('shahrazad-slow'), '1');
  assert.deepEqual(changed, ['slow']);
  const reloaded = await import('../../web/js/options.js?reloaded');
  assert.equal(reloaded.opts.slow, true, 'remembered after a reload');
});

test('text size goes up and down in steps, stops at each end, and is remembered', async () => {
  localStorage.clear();
  const options = await import('../../web/js/options.js?size');
  const changed = [];
  options.onOptionChange(name => changed.push(name));
  options.setupOptions();
  const scale = () => document.documentElement.style['--text-scale'];
  const larger = document.getElementById('o-larger'), smaller = document.getElementById('o-smaller');
  assert.equal(scale(), '1');
  assert.equal(document.getElementById('o-size').textContent, '100%');
  larger.onclick();
  assert.equal(scale(), '1.15');
  assert.equal(document.getElementById('o-size').textContent, '115%');
  assert.equal(localStorage.getItem('shahrazad-size'), '1.15');
  assert.deepEqual(changed, ['size']);
  for (let i = 0; i < 10; i++) larger.onclick();
  assert.equal(scale(), '1.5', 'no larger than the last step');
  assert.equal(larger.disabled, true);
  for (let i = 0; i < 10; i++) smaller.onclick();
  assert.equal(scale(), '0.85', 'no smaller than the first step');
  assert.equal(smaller.disabled, true);
  localStorage.setItem('shahrazad-size', '7');   // not one of the steps: back to normal
  assert.equal((await import('../../web/js/options.js?odd-size')).textSize, 1);
  localStorage.setItem('shahrazad-size', '1.3');
  assert.equal((await import('../../web/js/options.js?saved-size')).textSize, 1.3, 'remembered after a reload');
});

test('helpers', async () => {
  const util = await import('../../web/js/util.js');
  assert.equal(util.plural(1, 'turn'), '1 turn');
  assert.equal(util.plural(3, 'turn'), '3 turns');
  assert.ok(util.ARABIC_LETTER.test('كتب') && !util.ARABIC_LETTER.test('kataba'));
  assert.equal('كَتَبَ'.replace(util.VOWEL_MARKS, ''), 'كتب');
  const node = util.el('span', 'note', 'نص');
  assert.equal(node.tagName, 'SPAN');
  assert.equal(node.className, 'note');
  assert.equal(node.textContent, 'نص');

  const saved = globalThis.localStorage;
  globalThis.localStorage = {getItem() { throw new Error('private window'); }, setItem() { throw new Error('private window'); }};
  try {
    assert.equal(util.pref('x', 'fallback'), 'fallback', 'storage that fails falls back');
    util.setPref('x', '1');   // must not throw
  } finally {
    globalThis.localStorage = saved;
  }

  util.pinStatus('Tap anywhere to hear the reply.');
  util.setStatus('');
  assert.equal(document.getElementById('st').textContent, 'Tap anywhere to hear the reply.');
  util.setStatus('Searching the internet…');
  assert.equal(document.getElementById('st').textContent, 'Searching the internet…');
  util.pinStatus('');
  assert.equal(document.getElementById('st').textContent, 'Searching the internet…', 'a newer message stays');
  util.setStatus('');
  assert.equal(document.getElementById('st').textContent, '');
  util.pinStatus('Tap anywhere to hear the reply.');
  util.pinStatus('');
  assert.equal(document.getElementById('st').textContent, '', 'the request itself goes');
});

test('the server answers with an expired login: go to the login page', async () => {
  const util = await import('../../web/js/util.js');
  globalThis.fetch = async () => ({status: 401, json: async () => ({})});
  await assert.rejects(util.fetchJSON('progress'));
  assert.equal(location.href, 'login');
  let request = null;
  globalThis.fetch = async (path, init) => (request = {path, init}, {status: 200, json: async () => ({ok: 1})});
  assert.deepEqual(await util.fetchJSON('gloss', {word: 'كتب'}), {ok: 1});
  assert.equal(request.init.method, 'POST');
  assert.equal(request.init.body, '{"word":"كتب"}');
});
