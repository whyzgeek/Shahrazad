// The microphone, opened for each turn and released when it ends.
//
// While a page holds the microphone, phones treat it as a call: replies play at call volume, or not at all. Safari is
// also told when the page only plays sound.
import {note} from './diary.js';

let stream = null;
let context = null;

function setAudioSession(type) {
  try {
    if (navigator.audioSession) navigator.audioSession.type = type;
  } catch (e) {
    // Only Safari has this.
  }
}

/** Start recording; onChunk receives 16 kHz 16-bit PCM every 80 ms. Throws when the microphone is unavailable. */
export async function openMic(onChunk) {
  if (stream) return;
  setAudioSession('play-and-record');
  stream = await navigator.mediaDevices.getUserMedia({
    audio: {channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true},
  });
  context = new AudioContext();
  await context.audioWorklet.addModule(new URL('mic-worklet.js', import.meta.url));
  const node = new AudioWorkletNode(context, 'downsampler');
  context.createMediaStreamSource(stream).connect(node);
  node.port.onmessage = e => onChunk(e.data);
  await context.resume();
  note('microphone on');
}

export function closeMic() {
  if (!stream) return;
  stream.getTracks().forEach(track => track.stop());
  try {
    context.close();
  } catch (e) {
    // Already closed.
  }
  stream = context = null;
  setAudioSession('playback');
  note('microphone off');
}
