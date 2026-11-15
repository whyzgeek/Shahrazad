// The microphone (web/js/mic.js) and its downsampler (web/js/mic-worklet.js).
import './fake-browser.js';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

// ------------------------------------------------------------ a fake microphone and audio graph
const mic = {opened: 0, stoppedTracks: 0, refuse: false, contexts: []};
Object.defineProperty(globalThis, 'navigator', {configurable: true, value: {
  audioSession: {type: 'auto'},
  mediaDevices: {
    async getUserMedia(constraints) {
      if (mic.refuse) throw Object.assign(new Error('denied'), {name: 'NotAllowedError'});
      mic.opened++;
      mic.constraints = constraints;
      return {getTracks: () => [{stop: () => mic.stoppedTracks++}]};
    },
  },
}});   // Node has its own navigator, which can only be replaced this way
globalThis.AudioContext = class {
  constructor() {
    this.state = 'suspended';
    this.audioWorklet = {addModule: async url => (this.module = String(url))};
    mic.contexts.push(this);
  }
  createMediaStreamSource() {
    return {connect: node => (this.node = node)};
  }
  async resume() { this.state = 'running'; }
  close() { this.state = 'closed'; }
};
globalThis.AudioWorkletNode = class {
  constructor(context, name) {
    this.name = name;
    this.port = {onmessage: null};
  }
};

const {openMic, closeMic} = await import('../../web/js/mic.js');

test('opening the microphone records for a call, and closing it goes back to playback', async () => {
  const chunks = [];
  await openMic(pcm => chunks.push(pcm));
  const context = mic.contexts.at(-1);
  assert.equal(navigator.audioSession.type, 'play-and-record');
  assert.equal(context.state, 'running');
  assert.equal(context.node.name, 'downsampler');
  assert.ok(context.module.endsWith('/mic-worklet.js'));
  assert.equal(mic.constraints.audio.echoCancellation, true);
  context.node.port.onmessage({data: 'pcm'});
  assert.deepEqual(chunks, ['pcm']);
  closeMic();
  assert.equal(mic.stoppedTracks, 1, 'the microphone is released, so the phone leaves call mode');
  assert.equal(context.state, 'closed');
  assert.equal(navigator.audioSession.type, 'playback');
});

test('opening twice keeps one microphone, and closing twice is harmless', async () => {
  const before = mic.opened;
  await openMic(() => {});
  await openMic(() => {});
  assert.equal(mic.opened, before + 1);
  closeMic();
  closeMic();
});

test('a refused microphone throws, so the page can say so', async () => {
  mic.refuse = true;
  await assert.rejects(openMic(() => {}), {name: 'NotAllowedError'});
  mic.refuse = false;
  closeMic();
});

// ------------------------------------------------------------ the downsampler, run outside an audio thread
function loadDownsampler(rate) {
  let Processor = null;
  const source = readFileSync(new URL('../../web/js/mic-worklet.js', import.meta.url), 'utf8');
  class AudioWorkletProcessor {
    constructor() { this.port = {posted: [], postMessage: m => this.port.posted.push(m)}; }
  }
  new Function('AudioWorkletProcessor', 'registerProcessor', 'sampleRate', source)(
    AudioWorkletProcessor, (name, cls) => (Processor = cls), rate);
  return new Processor();
}

test('48 kHz becomes 16 kHz, in 80 ms chunks of 16-bit samples', () => {
  const d = loadDownsampler(48000);
  const block = new Float32Array(128).fill(0.5);
  for (let i = 0; i < 30; i++) assert.equal(d.process([[block]]), true);   // 3840 samples in: exactly one chunk out
  assert.equal(d.port.posted.length, 1);
  const pcm = new Int16Array(d.port.posted[0]);
  assert.equal(pcm.length, 1280);
  assert.ok(pcm.every(v => v === Math.trunc(0.5 * 32767)));
});

test('44.1 kHz also gives 16 kHz', () => {
  const d = loadDownsampler(44100);
  const second = new Float32Array(44100);
  for (let i = 0; i < second.length; i += 128) d.process([[second.subarray(i, i + 128)]]);
  const samples = d.port.posted.length * 1280 + d.filled;
  assert.ok(Math.abs(samples - 16000) <= 1, `${samples} samples for one second`);
});

test('loud input is clipped instead of wrapping around', () => {
  const d = loadDownsampler(16000);
  d.process([[new Float32Array(1280).fill(3)]]);
  assert.ok(new Int16Array(d.port.posted[0]).every(v => v === 32767));
});

test('no input yet (the microphone starting) is skipped', () => {
  const d = loadDownsampler(48000);
  assert.equal(d.process([[]]), true);
  assert.equal(d.port.posted.length, 0);
});
