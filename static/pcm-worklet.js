class CaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super(); this.buffer = new Float32Array(4096); this.used = 0;
    this.port.onmessage = ({data}) => { if (data === 'flush') this.flush(); };
  }
  flush() {
    if (this.used) {
      const chunk = this.buffer.slice(0, this.used);
      this.port.postMessage(chunk, [chunk.buffer]); this.used = 0;
    }
    this.port.postMessage('flushed');
  }
  process(inputs) {
    const samples = inputs[0]?.[0]; if (!samples) return true;
    for (let i = 0; i < samples.length; i++) {
      this.buffer[this.used++] = samples[i];
      if (this.used === this.buffer.length) {
        const chunk = this.buffer; this.port.postMessage(chunk, [chunk.buffer]);
        this.buffer = new Float32Array(4096); this.used = 0;
      }
    }
    return true;
  }
}
registerProcessor('pcm-capture', CaptureProcessor);
