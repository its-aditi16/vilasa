// Records the microphone straight to 16 kHz mono 16-bit WAV in the browser,
// so the server never needs ffmpeg for live calls. Auto-stops at 28 s (Prisma REST limit is 30 s).
// The mic stays open between turns in a call: asking for it each time would add a delay and flicker the browser's indicator.
window.WavRecorder = class WavRecorder {
  constructor({ rate = 16000, maxSeconds = 28 } = {}) {
    this.rate = rate;
    this.maxSeconds = maxSeconds;
    this.chunks = [];
    this.recording = false;
  }

  async open() {
    if (this.ctx) return;
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: false, autoGainControl: true },
    });
    this.ctx = new (window.AudioContext || window.webkitAudioContext)();
    if (this.ctx.state === "suspended") await this.ctx.resume();
    this.source = this.ctx.createMediaStreamSource(this.stream);
    this.node = this.ctx.createScriptProcessor(2048, 1, 1);
    this.node.onaudioprocess = (e) => {
      const samples = e.inputBuffer.getChannelData(0);
      if (this.recording) {
        this.chunks.push(new Float32Array(samples));
        if (this.length() / this.ctx.sampleRate >= this.maxSeconds && this.onLimit) this.onLimit();
      }
      if (this.onFrame) {
        let sum = 0;
        for (let i = 0; i < samples.length; i++) sum += samples[i] * samples[i];
        this.onFrame(Math.sqrt(sum / samples.length), (samples.length / this.ctx.sampleRate) * 1000);
      }
    };
    this.source.connect(this.node);
    this.node.connect(this.ctx.destination);
  }

  begin() {
    this.chunks = [];
    this.recording = true;
  }

  length() {
    return this.chunks.reduce((n, c) => n + c.length, 0);
  }

  // Ends the recording and returns the part between `from` and `to`, in seconds from begin().
  finish({ from = 0, to = Infinity } = {}) {
    if (!this.ctx || !this.recording) return null;
    this.recording = false;
    const srcRate = this.ctx.sampleRate;
    const all = new Float32Array(this.length());
    let off = 0;
    for (const c of this.chunks) { all.set(c, off); off += c.length; }
    this.chunks = [];
    const part = all.subarray(Math.max(0, Math.floor(from * srcRate)), Math.min(all.length, Math.ceil(to * srcRate)));
    const pcm = this.downsample(part, srcRate, this.rate);
    return { blob: this.encode(pcm, this.rate), seconds: pcm.length / this.rate };
  }

  async close() {
    if (!this.ctx) return;
    this.recording = false;
    this.onFrame = null;
    this.node.disconnect();
    this.source.disconnect();
    this.stream.getTracks().forEach((t) => t.stop());
    const ctx = this.ctx;
    this.ctx = null;
    await ctx.close();
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

// Decides when someone has started and stopped talking, from mic levels. Feed it one level per audio frame.
window.VoiceActivity = class VoiceActivity {
  constructor({ calibrateMs = 300, riseMs = 120, silenceMs = 900, maxMs = 15000, noSpeechMs = 6000 } = {}) {
    Object.assign(this, { calibrateMs, riseMs, silenceMs, maxMs, noSpeechMs });
    this.now = 0;
    this.noise = [];
    this.rise = 0;
    this.quiet = 0;
    this.speaking = false;
    this.speechStart = null; // ms from the first frame
    this.speechEnd = null;
  }

  // Returns "speech" when speech starts, "end" after the silence, "max" at the time limit, "no-speech" if nobody spoke.
  feed(level, ms) {
    if (this.done) return null;
    const event = this.step(level, ms);
    this.done = event !== null && event !== "speech";
    return event;
  }

  step(level, ms) {
    this.now += ms;
    if (this.now <= this.calibrateMs) { this.noise.push(level); return null; }
    if (this.startLevel === undefined) this.calibrate();

    if (!this.speaking) {
      this.rise = level >= this.startLevel ? this.rise + ms : 0;
      if (this.rise >= this.riseMs) {
        this.speaking = true;
        this.speechStart = this.now - this.rise;
        this.speechEnd = this.now;
        return "speech";
      }
      return this.now >= this.noSpeechMs ? "no-speech" : null;
    }
    if (level >= this.stopLevel) {
      this.quiet = 0;
      this.speechEnd = this.now;
    } else {
      this.quiet += ms;
    }
    if (this.quiet >= this.silenceMs) return "end";
    return this.now - this.speechStart >= this.maxMs ? "max" : null;
  }

  calibrate() {
    // The median ignores someone who starts talking during calibration; the cap stops a loud start hiding all speech.
    const sorted = [...this.noise].sort((a, b) => a - b);
    const floor = Math.min(sorted[Math.floor(sorted.length / 2)] || 0, 0.03);
    this.startLevel = Math.max(floor * 3, floor + 0.012);
    this.stopLevel = Math.max(floor * 1.8, floor + 0.006);
  }
};
