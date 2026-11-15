// Runs on the browser's audio thread: turns the microphone's samples (usually 48 kHz float) into 16 kHz 16-bit PCM,
// averaging the samples within each output sample, and posts it in chunks of 1280 samples (80 ms).
class Downsampler extends AudioWorkletProcessor {
  constructor() {
    super();
    this.ratio = sampleRate / 16000;
    this.sum = 0;
    this.count = 0;
    this.phase = 0;
    this.chunk = new Int16Array(1280);
    this.filled = 0;
  }

  process(inputs) {
    const samples = inputs[0][0];
    if (!samples) return true;
    for (let i = 0; i < samples.length; i++) {
      this.sum += samples[i];
      this.count++;
      this.phase++;
      if (this.phase >= this.ratio) {
        this.phase -= this.ratio;
        const value = Math.max(-1, Math.min(1, this.sum / this.count));
        this.sum = 0;
        this.count = 0;
        this.chunk[this.filled++] = value * 32767;
        if (this.filled === this.chunk.length) {
          this.port.postMessage(this.chunk.buffer.slice(0));
          this.filled = 0;
        }
      }
    }
    return true;
  }
}

registerProcessor('downsampler', Downsampler);
