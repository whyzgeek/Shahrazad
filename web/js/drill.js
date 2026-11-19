// "Repeat after me": a saved reply played slowly, a few words at a time, with a pause after each phrase for the learner
// to say it. The reply's own audio is cut, not synthesized again in pieces: the voice speaks short fragments badly.
// A sentence of up to 6 words stays whole.
//
// Where to cut: the text says how many words there are, so how long a word takes on average, and a sentence of more
// than 6 words is cut at the quietest moment (a pause between words) every 3 to 6 words' worth of speech.

const MIN_WORDS = 3;
const MAX_WORDS = 6;
const FRAME_S = 0.02;      // loudness is measured over 20 ms

/** How many words the voice says in this text. */
export const wordCount = text => text.split(/\s+/).filter(w => /\p{L}/u.test(w)).length;

/** Loudness of each 20 ms frame. */
function frames(samples, rate) {
  const size = Math.max(1, Math.round(rate * FRAME_S));
  const out = [];
  for (let i = 0; i + size <= samples.length; i += size) {
    let sum = 0;
    for (let j = i; j < i + size; j++) sum += samples[j] * samples[j];
    out.push(Math.sqrt(sum / size));
  }
  return out;
}

/** Sample positions where the audio of a sentence of this many words should be cut.
 *
 * The pieces aren't shown as text, so what matters is that each is a sensible length and ends at a real pause, not
 * that it matches the text's phrases exactly. From the start of each piece, the cut goes to the quietest moment
 * between about 2.5 and 6.5 words' worth of speech ahead (the gaps at commas and between phrases are the quietest),
 * and the rest stays whole once it fits in one piece. */
export function cutPoints(samples, rate, words) {
  if (words <= MAX_WORDS) return [];
  const raw = frames(samples, rate);
  const loud = raw.map((v, i) => (v + (raw[i - 1] ?? v) + (raw[i + 1] ?? v)) / 3);   // over 60 ms: no dips inside a word
  const peak = Math.max(...loud, 1e-9);
  const voiced = loud.map(v => v > peak * 0.05);
  const first = Math.max(0, voiced.indexOf(true));
  const last = Math.max(first + 1, voiced.lastIndexOf(true) + 1);
  const word = (last - first) / words;   // frames per word, on average
  const cuts = [];
  let start = first;
  while (last - start > (MAX_WORDS + 0.5) * word) {
    const lo = Math.round(start + (MIN_WORDS - 0.5) * word);
    const hi = Math.min(Math.round(start + (MAX_WORDS + 0.5) * word), Math.round(last - (MIN_WORDS - 1) * word));
    if (hi <= lo) break;
    let best = lo;
    for (let f = lo; f <= hi; f++) if (loud[f] < loud[best]) best = f;
    cuts.push(Math.round((best + 0.5) * rate * FRAME_S));
    start = best;
  }
  return cuts;
}

/** How long to wait after a phrase for the learner to say it: longer phrases get longer. */
export const pauseAfter = (seconds, rate) => seconds / rate * 1.5 + 1;

/** A WAV file of 16-bit mono samples. */
export function wav(samples, rate) {
  const view = new DataView(new ArrayBuffer(44 + samples.length * 2));
  const text = (at, s) => [...s].forEach((c, i) => view.setUint8(at + i, c.charCodeAt(0)));
  text(0, 'RIFF');
  view.setUint32(4, 36 + samples.length * 2, true);
  text(8, 'WAVEfmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, rate, true);
  view.setUint32(28, rate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  text(36, 'data');
  view.setUint32(40, samples.length * 2, true);
  samples.forEach((s, i) => view.setInt16(44 + i * 2, Math.max(-1, Math.min(1, s)) * 32767, true));
  return new Blob([view], {type: 'audio/wav'});
}

/** One sentence's audio (any format the browser plays) cut into phrases: [{blob, seconds}], or null to keep it whole. */
export async function split(bytes, text) {
  const words = wordCount(text);
  const Context = globalThis.OfflineAudioContext || globalThis.webkitOfflineAudioContext;
  if (words <= MAX_WORDS || !Context) return null;
  const rate = 16000;
  const audio = await new Context(1, 1, rate).decodeAudioData(bytes.slice(0));
  const samples = audio.getChannelData(0);
  const cuts = [0, ...cutPoints(samples, rate, words), samples.length];
  return cuts.slice(0, -1).map((start, i) => {
    const piece = samples.subarray(start, cuts[i + 1]);
    return {blob: wav(piece, rate), seconds: piece.length / rate};
  });
}
