(() => {
  const $ = (id) => document.getElementById(id);
  const STEPS = ["village", "landmark", "house", "confirm"];
  let session = null;
  let busy = false;
  let finished = false;
  let lastLang = null;
  let recorder = null;
  let currentAudio = null;
  const fixed = new Set();

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

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

  // ---------------------------------------------------------------- call
  async function startCall(id) {
    if (busy) return;
    busy = true;
    document.querySelectorAll(".job").forEach((j) => j.classList.toggle("active", j.id === `job-${id}`));
    $("chat").innerHTML = "";
    $("callEmpty").hidden = true;
    $("call").hidden = false;
    if (window.innerWidth < 1081) document.querySelector(".phone").scrollIntoView({ behavior: "smooth", block: "start" });
    lastLang = null;
    finished = false;
    setControls(true);
    try {
      const p = await api("/api/calls", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ delivery_id: id }) });
      session = p.session_id;
      render(p);
    } catch (e) { addError(e.message); }
    busy = false;
    setControls(finished);
  }

  function addMsg(who, text, meta, audioUrl) {
    const div = document.createElement("div");
    div.className = `msg ${who}`;
    div.innerHTML = esc(text) + (audioUrl ? ` <button class="play" title="Play again" aria-label="Play again">▶︎</button>` : "") + (meta ? `<span class="meta">${esc(meta)}</span>` : "");
    if (audioUrl) div.querySelector(".play").addEventListener("click", () => play(audioUrl));
    $("chat").appendChild(div);
    $("chat").scrollTop = $("chat").scrollHeight;
  }

  function addError(text) { addMsg("err", text); }

  function play(url) {
    try {
      if (currentAudio) currentAudio.pause();
      currentAudio = new Audio(url);
      currentAudio.play().catch(() => {});
    } catch (e) { /* audio optional */ }
  }

  function render(p) {
    if (p.heard) {
      const h = p.heard;
      const bits = [h.source === "prisma" ? "Prisma v3" : h.source];
      if (h.language) bits.push(h.language);
      if (h.latency) bits.push(`${(+h.latency).toFixed(2)}s`);
      if (h.keyterms) bits.push(`${h.keyterms} keyterms`);
      if (h.cached) bits.push("cached");
      addMsg("c", h.text || "(silence)", bits.join(" · "));
    }
    addMsg("v", p.reply.text, "", p.reply.audio_url);
    play(p.reply.audio_url);

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
    setRow("rVillage", "cVillage", c.village ? `${c.village}${area ? ", " + area : ""}` : "");
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
    if (c.maps_url) { m.hidden = false; m.href = c.maps_url; } else m.hidden = true;
    $("cWords").innerHTML = (c.customer_words || []).map((w) => `<li>${esc(w)}</li>`).join("");
  }

  async function sendTurn(form) {
    if (!session || busy) return;
    busy = true;
    setControls(true);
    try {
      const p = await api(`/api/calls/${session}/turn`, { method: "POST", body: form });
      render(p);
    } catch (e) { addError(e.message); }
    busy = false;
    setControls(finished);
  }

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
    const f = new FormData();
    f.append("text", t);
    sendTurn(f);
  });

  // scripted demo answer
  $("scripted").addEventListener("click", async () => {
    if (!session || busy) return;
    busy = true; setControls(true);
    try { render(await api(`/api/calls/${session}/scripted`, { method: "POST" })); } catch (e) { addError(e.message); }
    busy = false;
    setControls(finished);
  });

  // hold-to-talk
  const mic = $("mic");
  async function startRec(e) {
    e.preventDefault();
    if (!session || busy || recorder) return;
    if (currentAudio) currentAudio.pause();
    try {
      recorder = new WavRecorder();
      recorder.onLimit = stopRec;
      await recorder.start();
      mic.classList.add("rec");
      $("micLabel").textContent = "Listening… release to send";
    } catch (err) {
      recorder = null;
      addError("Microphone not available: " + err.message + ". Type the answer instead.");
    }
  }
  async function stopRec() {
    if (!recorder) return;
    const r = recorder;
    recorder = null;
    mic.classList.remove("rec");
    $("micLabel").textContent = "Hold to talk";
    const out = await r.stop();
    if (!out || out.seconds < 0.4) { addError("Too short — hold the button while you speak."); return; }
    const f = new FormData();
    f.append("audio", out.blob, "turn.wav");
    sendTurn(f);
  }
  mic.addEventListener("pointerdown", startRec);
  mic.addEventListener("pointerup", stopRec);
  mic.addEventListener("pointerleave", () => recorder && stopRec());
  document.addEventListener("keydown", (e) => { if (e.code === "Space" && document.activeElement === document.body && !e.repeat) startRec(e); });
  document.addEventListener("keyup", (e) => { if (e.code === "Space" && document.activeElement === document.body) stopRec(); });

  loadStatus();
  loadQueue();
})();
