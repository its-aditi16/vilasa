(() => {
  const $ = (id) => document.getElementById(id);
  const STEPS = ["village", "landmark", "house", "confirm"];
  const STATUS = { speaking: "Vilasa speaking", listening: "Listening…", thinking: "Thinking…", finished: "Call finished", idle: "" };
  const SILENT_WAV = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=";
  const MAX_ERRORS_IN_A_ROW = 2;
  let session = null;
  let busy = false;
  let finished = false;
  let lastLang = null;
  let phase = "idle";
  let holding = false;
  let vad = null; // set while hands-free is listening
  let speechToken = 0;
  let errorsInARow = 0;
  const recorder = new WavRecorder();
  const speaker = new Audio();
  const fixed = new Set();

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const handsFree = () => $("handsFree").checked;

  async function api(path, opts = {}) {
    const res = await fetch(path, opts);
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.message || body.detail || `HTTP ${res.status}`);
    return body;
  }

  // ---------------------------------------------------------------- status + queue
  async function loadStatus() {
    try {
      const s = await api("/api/status");
      const mode = $("mode");
      mode.textContent = s.mode === "live" ? "LIVE · Gnani API" : "MOCK · no credits used";
      mode.className = "pill " + s.mode;
      const u = s.usage || {};
      $("usage").textContent = s.mode === "live" ? `${u.stt_calls} STT calls · ${u.stt_seconds}s · ${u.tts_chars} TTS chars` : "";
      $("demoBanner").hidden = !s.demo_pin_data;
    } catch (e) { /* ignore */ }
  }

  async function loadQueue() {
    const list = await api("/api/deliveries");
    $("queue").innerHTML = list.map((d) => `
      <li class="job ${fixed.has(d.id) ? "fixed" : ""}" id="job-${esc(d.id)}">
        <div class="job-top"><span class="job-name">${esc(d.customer)}</span><span class="job-id">${esc(d.id)}</span></div>
        <div class="job-addr">${esc(d.typed_address)} · PIN ${esc(d.pin)}</div>
        <div class="job-why">${esc(d.failure)} · ${esc(d.attempts)} attempt${d.attempts > 1 ? "s" : ""}</div>
        <div class="job-foot">
          <span class="muted small">${esc(d.item)}</span>
          ${fixed.has(d.id) ? `<span class="done-tag">✓ Address fixed</span>` : `<button class="btn" data-call="${esc(d.id)}">Call with Vilasa</button>`}
        </div>
      </li>`).join("");
    $("queue").querySelectorAll("[data-call]").forEach((b) => b.addEventListener("click", () => startCall(b.dataset.call)));
  }

  // ---------------------------------------------------------------- call status
  function setPhase(next) {
    phase = next;
    const line = $("callStatus");
    line.textContent = STATUS[next];
    line.dataset.phase = next;
    if (next !== "listening") showLevel(0, false);
  }

  function showLevel(level, voice) {
    const fill = $("levelFill");
    fill.style.width = `${Math.min(100, Math.sqrt(level) * 220)}%`;
    fill.classList.toggle("voice", !!voice);
  }

  // ---------------------------------------------------------------- speaking
  function stopSpeaking() {
    speechToken++;
    speaker.pause();
  }

  function speak(url) {
    stopListening();
    const token = ++speechToken;
    setPhase("speaking");
    const after = () => {
      if (token !== speechToken) return;
      speechToken++;
      afterSpeech();
    };
    speaker.onended = after;
    speaker.onerror = after;
    speaker.src = url;
    speaker.play().catch(after); // no audio is no reason to stop the call
  }

  function afterSpeech() {
    if (finished) { endOfCall(); return; }
    setPhase("idle");
    setTimeout(listen, 150); // let the room settle so the mic doesn't hear the end of the prompt
  }

  function endOfCall() {
    setPhase("finished");
    recorder.close();
    if (window.innerWidth < 1081) $("card").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  // ---------------------------------------------------------------- hands-free
  function micFailed(err) {
    $("handsFree").checked = false;
    addError(`Microphone not available: ${err.message}. Hands-free is off. Type the answer instead.`);
  }

  async function listen() {
    if (!handsFree() || !session || finished || busy || holding || vad || phase !== "idle") return;
    if (document.activeElement === $("typedInput")) return; // they are typing
    const listener = new VoiceActivity();
    vad = listener;
    setPhase("listening");
    try {
      await recorder.open();
    } catch (err) {
      vad = null;
      setPhase("idle");
      micFailed(err);
      return;
    }
    if (vad !== listener) return; // cancelled while the mic was opening
    recorder.begin();
    recorder.onFrame = (level, ms) => {
      const event = listener.feed(level, ms);
      showLevel(level, listener.speaking);
      if (event === "end" || event === "max") {
        const to = (listener.speechEnd + 300) / 1000;
        const out = recorder.finish({ from: Math.max(0, listener.speechStart - 300) / 1000, to });
        stopListening();
        sendAudio(out);
      } else if (event === "no-speech") {
        stopListening();
        const f = new FormData();
        f.append("no_speech", "true");
        sendTurn(f);
      }
    };
  }

  function stopListening() {
    if (!vad) return;
    vad = null;
    recorder.onFrame = null;
    recorder.recording = false;
    setPhase("idle");
  }

  function sendAudio(out) {
    const f = new FormData();
    f.append("audio", out.blob, "turn.wav");
    sendTurn(f);
  }

  $("handsFree").addEventListener("change", () => {
    if (handsFree()) { recorder.open().catch(micFailed); listen(); return; }
    stopListening();
    if (!holding) recorder.close();
  });

  // ---------------------------------------------------------------- call
  async function startCall(id) {
    if (busy) return;
    busy = true;
    stopListening();
    stopSpeaking();
    speaker.src = SILENT_WAV; // phones only let audio play later if it started during this tap
    speaker.play().catch(() => {});
    if (handsFree()) recorder.open().catch(micFailed); // ask for the mic now, while the person is here to answer
    document.querySelectorAll(".job").forEach((j) => j.classList.toggle("active", j.id === `job-${id}`));
    $("chat").innerHTML = "";
    $("callEmpty").hidden = true;
    $("call").hidden = false;
    if (window.innerWidth < 1081) document.querySelector(".phone").scrollIntoView({ behavior: "smooth", block: "start" });
    lastLang = null;
    finished = false;
    errorsInARow = 0;
    setControls(true);
    setPhase("thinking");
    try {
      const p = await api("/api/calls", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ delivery_id: id }) });
      session = p.session_id;
      busy = false;
      render(p);
    } catch (e) { busy = false; setPhase("idle"); addError(e.message); }
    setControls(finished);
  }

  function addMsg(who, text, meta, audioUrl) {
    const div = document.createElement("div");
    div.className = `msg ${who}`;
    div.innerHTML = esc(text) + (audioUrl ? ` <button class="play" title="Play again" aria-label="Play again">▶︎</button>` : "") + (meta ? `<span class="meta">${esc(meta)}</span>` : "");
    if (audioUrl) div.querySelector(".play").addEventListener("click", () => speak(audioUrl));
    $("chat").appendChild(div);
    $("chat").scrollTop = $("chat").scrollHeight;
  }

  function addError(text) { addMsg("err", text); }

  function render(p) {
    if (p.heard) {
      const h = p.heard;
      const bits = [h.source === "prisma" ? "Prisma v3" : h.source];
      if (h.language) bits.push(h.language);
      if (h.keyterms) bits.push(`${h.keyterms} keyterms`);
      if (h.cached) bits.push("cached");
      if (h.stt_ms) bits.push(`STT ${h.stt_ms} ms`);
      if (p.turn_ms !== undefined) bits.push(`turn ${p.turn_ms} ms`);
      addMsg("c", h.text || "(silence)", bits.join(" · "));
    }
    addMsg("v", p.reply.text, "", p.reply.audio_url);

    const lang = $("lang");
    lang.hidden = false;
    lang.textContent = p.card.language;
    if (lastLang && lastLang !== p.card.language) { lang.classList.remove("flash"); void lang.offsetWidth; lang.classList.add("flash"); }
    lastLang = p.card.language;

    const idx = STEPS.indexOf(p.state);
    document.querySelectorAll("#steps li").forEach((li, i) => {
      li.classList.toggle("now", i === idx);
      li.classList.toggle("ok", p.finished ? p.state === "done" || i < 3 : i < idx);
    });
    renderCard(p.card);
    finished = p.finished;
    if (p.finished) {
      if (p.card.status === "confirmed") { fixed.add(p.card.delivery_id); loadQueue(); }
    }
    loadStatus();
    speak(p.reply.audio_url);
  }

  function setRow(rowId, valueId, value) {
    const el = $(valueId);
    const next = value || "—";
    if (el.textContent !== next) {
      el.textContent = next;
      const row = $(rowId);
      row.classList.remove("fresh"); void row.offsetWidth; if (value) row.classList.add("fresh");
    }
  }

  function renderCard(c) {
    $("cardEmpty").hidden = true;
    $("card").hidden = false;
    $("cBefore").textContent = `${c.before} · PIN ${c.pin_on_parcel}`;
    const d = document.querySelector(`#job-${CSS.escape(c.delivery_id)} .job-why`);
    $("cFail").textContent = d ? d.textContent : "";
    const area = c.taluk ? `${c.taluk} taluk` : (c.district ? `${c.district} district` : "");
    setRow("rVillage", "cVillage", c.village ? `${c.village}${area ? ", " + area : ""}${c.village_or ? " " + c.village_or : ""}` : "");
    const pin = $("cPin");
    if (c.pin_corrected) { pin.hidden = false; pin.className = "badge fix"; pin.textContent = `PIN ${c.pin_on_parcel} → ${c.pin_corrected}`; }
    else if (c.village && c.village_confident) { pin.hidden = false; pin.className = "badge"; pin.textContent = `matched ${Math.round(c.village_score)}%`; }
    else pin.hidden = true;
    setRow("rLandmark", "cLandmark", c.landmark);
    setRow("rHouse", "cHouse", c.house);
    $("cLang").textContent = c.language + (c.language_switched ? " (switched)" : "");
    const st = $("cardState");
    st.hidden = false;
    st.textContent = c.status;
    st.className = "state " + (c.status === "confirmed" ? "confirmed" : "");
    const m = $("cMaps");
    if (c.maps_url && c.village) { m.hidden = false; m.href = c.maps_url; } else m.hidden = true;
    const line = $("cFixed");
    line.hidden = !(c.status === "confirmed" && c.call_seconds !== null);
    if (!line.hidden) line.textContent = `Address fixed in ${Math.round(c.call_seconds)} seconds · ${c.turns} turn${c.turns === 1 ? "" : "s"}`;
    $("cWords").innerHTML = (c.customer_words || []).map((w) => `<li>${esc(w)}</li>`).join("");
  }

  async function runTurn(request) {
    if (!session || busy) return;
    busy = true;
    stopListening();
    stopSpeaking();
    setControls(true);
    setPhase("thinking");
    let reply = null;
    try {
      reply = await request();
      errorsInARow = 0;
    } catch (e) {
      errorsInARow++;
      addError(e.message);
    }
    busy = false;
    setControls(finished);
    if (reply) { render(reply); setControls(finished); return; }
    setPhase("idle");
    if (errorsInARow < MAX_ERRORS_IN_A_ROW) listen(); // a bad moment shouldn't end hands-free; repeated failures should
  }

  const sendTurn = (form) => runTurn(() => api(`/api/calls/${session}/turn`, { method: "POST", body: form }));

  function setControls(disabled) {
    ["mic", "scripted"].forEach((id) => ($(id).disabled = disabled));
    $("typedInput").disabled = disabled;
  }

  // typed answer
  $("typed").addEventListener("submit", (e) => {
    e.preventDefault();
    const t = $("typedInput").value.trim();
    if (!t) return;
    $("typedInput").value = "";
    $("typedInput").blur();
    const f = new FormData();
    f.append("text", t);
    sendTurn(f);
  });
  $("typedInput").addEventListener("focus", () => { if (vad) stopListening(); });
  $("typedInput").addEventListener("blur", () => { if (!$("typedInput").value) setTimeout(listen, 150); });

  // scripted demo answer
  $("scripted").addEventListener("click", () => runTurn(() => api(`/api/calls/${session}/scripted`, { method: "POST" })));

  // hold-to-talk
  const mic = $("mic");
  async function startRec(e) {
    e.preventDefault();
    if (!session || busy || holding || finished) return;
    stopListening();
    stopSpeaking();
    holding = true;
    mic.classList.add("rec");
    $("micLabel").textContent = "Listening… release to send";
    setPhase("listening");
    try {
      await recorder.open();
      if (!holding) return; // already released
      recorder.begin();
      recorder.onLimit = stopRec;
      recorder.onFrame = (level) => showLevel(level, true);
    } catch (err) {
      holding = false;
      mic.classList.remove("rec");
      $("micLabel").textContent = "Hold to talk";
      setPhase("idle");
      addError("Microphone not available: " + err.message + ". Type the answer instead.");
    }
  }
  function stopRec() {
    if (!holding) return;
    holding = false;
    mic.classList.remove("rec");
    $("micLabel").textContent = "Hold to talk";
    recorder.onFrame = null;
    recorder.onLimit = null;
    const out = recorder.finish();
    setPhase("idle");
    if (!out || out.seconds < 0.4) {
      addError("Too short — hold the button while you speak.");
      listen();
      return;
    }
    sendAudio(out);
  }
  mic.addEventListener("pointerdown", startRec);
  mic.addEventListener("pointerup", stopRec);
  mic.addEventListener("pointerleave", () => holding && stopRec());
  document.addEventListener("keydown", (e) => { if (e.code === "Space" && document.activeElement === document.body && !e.repeat) startRec(e); });
  document.addEventListener("keyup", (e) => { if (e.code === "Space" && document.activeElement === document.body) stopRec(); });

  loadStatus();
  loadQueue();
})();
