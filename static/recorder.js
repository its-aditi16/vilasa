// Records the microphone straight to 16 kHz mono 16-bit WAV in the browser,
// so the server never needs ffmpeg for live calls. Auto-stops at 28 s (Prisma REST limit is 30 s).
window.WavRecorder = class WavRecorder {
  constructor({ rate = 16000, maxSeconds = 28 } = {}) {
    this.rate = rate;
    this.maxSeconds = maxSeconds;
    this.chunks = [];
  }

  async start() {
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: false, autoGainControl: true },
    });
    this.ctx = new (window.AudioContext || window.webkitAudioContext)();
    this.source = this.ctx.createMediaStreamSource(this.stream);
    this.node = this.ctx.createScriptProcessor(4096, 1, 1);
    this.chunks = [];
    this.node.onaudioprocess = (e) => {
      this.chunks.push(new Float32Array(e.inputBuffer.getChannelData(0)));
      if (this.length() / this.ctx.sampleRate >= this.maxSeconds && this.onLimit) this.onLimit();
    };
    this.source.connect(this.node);
    this.node.connect(this.ctx.destination);
  }

  length() {
    return this.chunks.reduce((n, c) => n + c.length, 0);
  }

  async stop() {
    if (!this.ctx) return null;
    const srcRate = this.ctx.sampleRate;
    this.node.disconnect();
    this.source.disconnect();
    this.stream.getTracks().forEach((t) => t.stop());
    await this.ctx.close();
    this.ctx = null;
    const all = new Float32Array(this.length());
    let off = 0;
    for (const c of this.chunks) { all.set(c, off); off += c.length; }
    const pcm = this.downsample(all, srcRate, this.rate);
    return { blob: this.encode(pcm, this.rate), seconds: pcm.length / this.rate };
  }

  downsample(x, src, dst) {
    if (dst >= src) return x;
    const ratio = src / dst;
    const out = new Float32Array(Math.floor(x.length / ratio));
    for (let i = 0; i < out.length; i++) {
      const a = Math.floor(i * ratio), b = Math.min(x.length, Math.floor((i + 1) * ratio));
      let s = 0;
      for (let j = a; j < b; j++) s += x[j];
      out[i] = s / Math.max(1, b - a);
    }
    return out;
  }

  encode(pcm, rate) {
    const buf = new ArrayBuffer(44 + pcm.length * 2);
    const v = new DataView(buf);
    const str = (o, s) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
    str(0, "RIFF"); v.setUint32(4, 36 + pcm.length * 2, true); str(8, "WAVE");
    str(12, "fmt "); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
    v.setUint32(24, rate, true); v.setUint32(28, rate * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true);
    str(36, "data"); v.setUint32(40, pcm.length * 2, true);
    for (let i = 0; i < pcm.length; i++) {
      const s = Math.max(-1, Math.min(1, pcm[i]));
      v.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    }
    return new Blob([buf], { type: "audio/wav" });
  }
};
