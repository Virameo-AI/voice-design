// Voice Design dashboard. Vanilla TypeScript over the engine API.
// Pages: Playground → Voices → Studio → Downloads → Connect.
import { api, ApiError, type Download, type Job, type Style, type Template, type Version, type Voice } from "./api.ts";
import { loadToken, saveToken } from "./config.ts";

const PALETTES = [
  ["#7c3aed", "#ec4899", "#f97316"],
  ["#06b6d4", "#3b82f6", "#8b5cf6"],
  ["#10b981", "#06b6d4", "#a3e635"],
  ["#f43f5e", "#f97316", "#facc15"],
  ["#8b5cf6", "#22d3ee", "#f472b6"],
  ["#f59e0b", "#ef4444", "#ec4899"],
] as const;
const PAGES: Record<string, [string, string]> = {
  playground: ["Playground", "Qwen VoiceDesign. Test a description, then keep a take."],
  voices: ["Voices", "Saved voices. Studio and agents read from here."],
  studio: ["Studio", "Qwen speaks the script. [pause 0.8s] sets a gap between beats."],
  downloads: ["Downloads", "Finished audio for video edits, uploads, and agents."],
  connect: ["Connect", "Every control on this page is a field on the API and on MCP."],
};
const ORDER = ["playground", "voices", "studio", "downloads", "connect"];
const PAGE_SIZE = { presets: 4, takes: 4, voices: 6, downloads: 8, beats: 5 } as const;
const STYLE_NOTES: Record<string, string> = {
  narration: "Steady pace and longer pauses. Good for explainers and documentaries.",
  comedy: "Quicker and brighter, with a lift on every line.",
  commercial: "Tight, even, forward. Short pauses and a louder finish.",
  kids: "Slower and warmer with a happy lift. The voice itself stays the same person.",
};

interface Take {
  index: number;
  file: string;
  url: string;
  seed: number | null;
  seconds: number;
  ok: boolean;
  warnings: string[];
  saved: string | null;
}

const state = {
  page: "playground",
  templates: [] as Template[],
  preset: null as string | null,
  takeCount: 4,
  takes: [] as Take[],
  designJob: null as Job | null,
  generating: false,
  playgroundId: null as string | null,
  playgrounds: [] as { id: string; name: string }[],
  listPage: { presets: 0, takes: 0, voices: 0, downloads: 0, beats: 0 },
  voices: [] as Voice[],
  versions: {} as Record<string, Version[]>,
  styles: [] as Style[],
  voiceId: null as string | null,
  versionId: null as string | null,
  style: "narration",
  steadiness: null as number | null,
  rendering: false,
  renderJob: null as Job | null,
  downloads: [] as Download[],
  filter: "all",
  health: null as Awaited<ReturnType<typeof api.health>> | null,
  mcp: null as boolean | null,
  current: null as { key: string; title: string; sub: string; pal: number; path: string; downloadName: string } | null,
};

const $ = <T extends HTMLElement = HTMLElement>(id: string) => document.getElementById(id) as T;
const esc = (s: unknown) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c] as string);
const orbVars = (i: number) => {
  const [a, b, c] = PALETTES[((i % PALETTES.length) + PALETTES.length) % PALETTES.length]!;
  return `--a:${a};--b:${b};--c:${c}`;
};
const fmt = (s: number) => {
  s = Math.max(0, Math.round(s || 0));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
};
const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 50) || "voice";
const hash = (s: string) => [...s].reduce((h, c) => Math.imul(h ^ c.charCodeAt(0), 0x9e3779b1) >>> 0, 0x811c9dc5);
const palOf = (id: string) => hash(id) % PALETTES.length;
const voiceById = (id: string | null) => state.voices.find((v) => v.voice_id === id);
const when = (iso: string) => {
  const d = new Date(iso);
  const today = new Date();
  const same = d.toDateString() === today.toDateString();
  return same ? `Today ${d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}` : d.toLocaleDateString([], { month: "short", day: "numeric" }) + " " + d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
};
const num = (id: string): number | undefined => {
  const raw = $<HTMLInputElement>(id).value.trim();
  if (!raw) return undefined;
  const v = Number(raw);
  return Number.isFinite(v) ? v : undefined;
};
const errText = (err: unknown) => (err instanceof Error ? err.message : String(err));

function wave(seed: number, on: boolean, n = 56) {
  let s = seed | 0;
  const r = () => {
    s = (s + 0x6d2b79f5) | 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  const h = 34;
  let out = "";
  for (let i = 0; i < n; i++) {
    const env = Math.sin((Math.PI * (i + 0.5)) / n) * 0.55 + 0.45;
    const bh = Math.max(2, Math.max(0.1, r() * env) * h);
    out += `<rect x="${i * 4}" y="${(h - bh) / 2}" width="2.4" height="${bh}" rx="1.2"/>`;
  }
  return `<svg class="wave ${on ? "on" : ""}" viewBox="0 0 ${n * 4} ${h}" preserveAspectRatio="none" aria-hidden="true">${out}</svg>`;
}
const PLAY = `<svg width="12" height="12" viewBox="0 0 12 12"><path d="M3 1.8v8.4L10 6Z" fill="currentColor"/></svg>`;
const PAUSE = `<svg width="12" height="12" viewBox="0 0 12 12"><path d="M3 2h2v8H3zM7 2h2v8H7z" fill="currentColor"/></svg>`;
const DL = `<svg width="13" height="13" viewBox="0 0 16 16" fill="none"><path d="M8 2.5v8m0 0L5 7.5m3 3 3-3M3 13.5h10" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>`;

/* toast */
let toastTimer: ReturnType<typeof setTimeout>;
function toast(text: string, action?: { label: string; run: () => void }, ms?: number) {
  $("toast-text").textContent = text;
  const btn = $<HTMLButtonElement>("toast-action");
  btn.hidden = !action;
  if (action) {
    btn.textContent = action.label;
    btn.onclick = () => {
      action.run();
      $("toast").classList.remove("show");
    };
  }
  $("toast").classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => $("toast").classList.remove("show"), ms ?? (action ? 6000 : 3200));
}
function fail(err: unknown, context: string) {
  const message = errText(err);
  if (err instanceof ApiError && err.status === 401) {
    toast("The server wants a bearer token. Paste it on Connect.", { label: "Open Connect", run: () => go("connect", "token") });
    return;
  }
  // Status 0 is a network failure: refresh the API and MCP dots right away instead of on the next 30 s tick.
  if (err instanceof ApiError && err.status === 0) void checkHealth();
  toast(`${context}: ${message}`, undefined, 7000);
}

/* navigation */
function go(page: string, focus?: string) {
  state.page = page;
  ORDER.forEach((p) => $(`page-${p}`).classList.toggle("active", p === page));
  document.querySelectorAll<HTMLButtonElement>(".nav-btn").forEach((b) => {
    if (b.dataset.go === page) b.setAttribute("aria-current", "page");
    else b.removeAttribute("aria-current");
  });
  const [title, subtitle] = PAGES[page] ?? PAGES.playground!;
  $("title").textContent = title;
  $("subtitle").textContent = subtitle;
  if (page === "studio") {
    renderStrip();
    renderBeats();
  }
  if (page === "downloads") void loadDownloads();
  if (page === "voices") void loadVoices();
  if (focus) setTimeout(() => $(focus)?.focus(), 0);
  history.replaceState(null, "", `#${page}`);
}

/* player: one <audio> element, protected WAVs fetched as blobs */
const audio = $<HTMLAudioElement>("audio");
const blobCache = new Map<string, string>();
async function urlFor(path: string): Promise<string> {
  const cached = blobCache.get(path);
  if (cached) return cached;
  const url = await api.blobUrl(path);
  blobCache.set(path, url);
  return url;
}
function playing(): boolean {
  return !audio.paused && !audio.ended;
}
async function play(item: NonNullable<typeof state.current>) {
  if (state.current?.key === item.key) {
    if (playing()) audio.pause();
    else void audio.play().catch(() => undefined);
    paintPlayer();
    return;
  }
  state.current = item;
  paintPlayer();
  try {
    audio.src = await urlFor(item.path);
    await audio.play();
  } catch (err) {
    // Browsers refuse autoplay before the first click; the player bar still shows the clip.
    if (!(err instanceof DOMException && err.name === "NotAllowedError")) fail(err, "Could not play");
  }
  paintPlayer();
}
function paintPlayer() {
  const c = state.current;
  if (!c) return;
  const on = playing();
  $("p-orb").setAttribute("style", orbVars(c.pal));
  $("p-orb").classList.toggle("spin", on);
  $("p-title").textContent = c.title;
  $("p-sub").textContent = c.sub;
  $("p-dur").textContent = fmt(audio.duration || 0);
  $("p-cur").textContent = fmt(audio.currentTime || 0);
  $("p-fill").style.width = audio.duration ? `${(audio.currentTime / audio.duration) * 100}%` : "0%";
  $("p-play").innerHTML = on ? PAUSE : PLAY;
  $("p-play").setAttribute("aria-label", on ? "Pause" : "Play");
  document.querySelectorAll<HTMLButtonElement>("[data-play-key]").forEach((b) => {
    const active = on && b.dataset.playKey === c.key;
    b.innerHTML = active ? PAUSE : PLAY;
    b.closest(".take")?.classList.toggle("playing", active);
  });
}
audio.addEventListener("timeupdate", paintPlayer);
audio.addEventListener("play", paintPlayer);
audio.addEventListener("pause", paintPlayer);
audio.addEventListener("ended", paintPlayer);
audio.addEventListener("loadedmetadata", paintPlayer);

async function downloadFile(path: string, name: string) {
  try {
    const url = await urlFor(path);
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    a.click();
  } catch (err) {
    fail(err, "Download failed");
  }
}

/* playground */
function pageWindow<T>(items: T[], key: keyof typeof PAGE_SIZE): { rows: T[]; page: number; pages: number; start: number } {
  const size = PAGE_SIZE[key];
  const pages = Math.max(1, Math.ceil(items.length / size));
  const page = Math.min(Math.max(0, state.listPage[key]), pages - 1);
  state.listPage[key] = page;
  return { rows: items.slice(page * size, page * size + size), page, pages, start: page * size };
}
function pagerHtml(key: keyof typeof PAGE_SIZE, page: number, pages: number): string {
  if (pages <= 1) return "";
  return `<button type="button" data-page-for="${key}" data-page-to="${page - 1}" ${page === 0 ? "disabled" : ""}>Previous</button><span>${page + 1} of ${pages}</span><button type="button" data-page-for="${key}" data-page-to="${page + 1}" ${page >= pages - 1 ? "disabled" : ""}>Next</button>`;
}
function renderPresets() {
  const windowed = pageWindow(state.templates, "presets");
  $("presets").innerHTML = windowed.rows
    .map(
      (t, i) => `
    <button type="button" class="preset" data-preset="${esc(t.id)}" aria-pressed="${t.id === state.preset}" title="${esc(t.role)}">
      <span class="orb" style="${orbVars(windowed.start + i)}"></span><span class="name">${esc(t.name)}</span>
    </button>`,
    )
    .join("");
  $("preset-pager").innerHTML = pagerHtml("presets", windowed.page, windowed.pages);
}
function applyPreset(id: string) {
  const t = state.templates.find((x) => x.id === id);
  if (!t) return;
  state.preset = id;
  const index = state.templates.findIndex((x) => x.id === id);
  if (index >= 0) state.listPage.presets = Math.floor(index / PAGE_SIZE.presets);
  $<HTMLTextAreaElement>("instruct").value = t.instruct;
  $<HTMLTextAreaElement>("sample").value = t.text;
  $<HTMLSelectElement>("language").value = t.language;
  if (t.params.temperature) $<HTMLInputElement>("d-temp").value = String(t.params.temperature);
  renderPresets();
}
function renderPlaygroundPick() {
  const sel = $<HTMLSelectElement>("playground-pick");
  sel.innerHTML =
    `<option value="">New playground</option>` + state.playgrounds.map((p) => `<option value="${esc(p.id)}" ${p.id === state.playgroundId ? "selected" : ""}>${esc(p.name)}</option>`).join("");
}
function designParams() {
  const params: Record<string, number> = {};
  const temp = num("d-temp");
  const topp = num("d-topp");
  const topk = num("d-topk");
  const rep = num("d-rep");
  const tokens = num("d-tokens");
  if (temp) params.temperature = temp;
  if (topp) params.top_p = topp;
  if (topk) params.top_k = topk;
  if (rep) params.repetition_penalty = rep;
  if (tokens) params.max_tokens = tokens;
  return params;
}
function renderTakes() {
  const box = $("takes");
  $("step-2").classList.toggle("on", state.takes.length > 0 || state.generating);
  $("step-3").classList.toggle("on", state.takes.some((t) => t.saved));
  if (state.generating) {
    box.innerHTML = Array.from({ length: state.takeCount }, () => `<div class="skeleton"></div>`).join("");
    const p = state.designJob?.progress;
    $("takes-note").textContent = p && p.total ? `${p.detail} (${p.completed} of ${p.total})` : "Queued…";
    $("take-pager").innerHTML = "";
    return;
  }
  if (!state.takes.length) {
    box.innerHTML = `<div class="empty-takes" style="grid-column:1/-1">
      <div class="orb" style="--s:44px;margin:0 auto 10px;${orbVars(0)}"></div>
      <b style="color:var(--ink)">Pick a starting point, then Generate.</b><br>Takes appear here with a play button and a Keep button on each.</div>`;
    $("takes-note").textContent = "";
    $("take-pager").innerHTML = "";
    return;
  }
  const windowed = pageWindow(state.takes, "takes");
  $("takes-note").textContent = "Play, then Keep. The kept take becomes a saved voice.";
  box.innerHTML = windowed.rows
    .map(
      (t) => `
    <article class="take">
      <div class="take-head">
        <div class="orb" style="${orbVars(t.index - 1)}"></div>
        <div class="grow"><strong>Take ${t.index}</strong><span class="muted" style="font-size:13px">${t.seconds.toFixed(1)} s · seed ${t.seed ?? "–"}</span></div>
        <button class="play" type="button" data-play-key="take-${t.index - 1}" data-take="${t.index - 1}" aria-label="Play take ${t.index}">${PLAY}</button>
      </div>
      <div style="${orbVars(t.index - 1)}">${wave(t.seed ?? t.index, true)}</div>
      <div class="checks">${t.ok ? `<span class="chip ok">clean</span>` : ""}${t.warnings.map((w) => `<span class="chip warn">${esc(w.replace(/_/g, " "))}</span>`).join("")}</div>
      <div class="foot">
        ${t.saved ? `<button class="btn sm saved-btn" type="button" data-narrate="${esc(t.saved)}">Saved · Narrate</button>` : `<button class="btn sm dark" type="button" data-keep="${t.index - 1}">Keep</button>`}
      </div>
    </article>`,
    )
    .join("");
  $("take-pager").innerHTML = pagerHtml("takes", windowed.page, windowed.pages);
  paintPlayer();
}
async function ensurePlayground(config: Record<string, unknown>): Promise<string> {
  if (state.playgroundId) {
    await api.updatePlayground(state.playgroundId, { config });
    return state.playgroundId;
  }
  const template = state.templates.find((t) => t.id === state.preset);
  const name = template ? template.name : `Custom ${new Date().toLocaleDateString([], { month: "short", day: "numeric" })}`;
  const created = await api.createPlayground({ name, template_id: template?.id ?? null, config });
  state.playgroundId = created.id;
  state.playgrounds.unshift({ id: created.id, name: created.name });
  renderPlaygroundPick();
  return created.id;
}
async function generate() {
  if (state.generating) return;
  const instruct = $<HTMLTextAreaElement>("instruct").value.trim();
  const text = $<HTMLTextAreaElement>("sample").value.trim();
  if (!instruct) {
    toast("Describe the voice first.");
    $("instruct").focus();
    return;
  }
  if (!text) {
    toast("Add a sample line for the takes to read.");
    $("sample").focus();
    return;
  }
  const config = {
    instruct,
    text,
    language: $<HTMLSelectElement>("language").value,
    candidates: state.takeCount,
    seed_start: num("seed") ?? 1000,
    params: designParams(),
  };
  state.generating = true;
  state.takes = [];
  state.listPage.takes = 0;
  $<HTMLButtonElement>("generate").disabled = true;
  renderTakes();
  try {
    const playgroundId = await ensurePlayground(config);
    const job = await api.runPlayground(playgroundId, { save: false });
    state.designJob = job;
    const done = await api.waitJob(job.id, (j) => {
      state.designJob = j;
      renderTakes();
    });
    if (done.status !== "succeeded") throw new Error(done.error ?? done.status);
    state.takes = done.outputs.map((o, i) => ({
      index: i + 1,
      file: o.file,
      url: o.url ?? `/v1/jobs/${done.id}/files/${o.file}`,
      seed: o.seed,
      seconds: o.checks.duration_s,
      ok: o.checks.ok,
      warnings: o.checks.warnings,
      saved: null,
    }));
    toast(`${state.takes.length} takes ready. Press Space to hear the first.`);
  } catch (err) {
    fail(err, "Design failed");
  } finally {
    state.generating = false;
    $<HTMLButtonElement>("generate").disabled = false;
    renderTakes();
  }
}
async function keep(i: number): Promise<string | null> {
  const take = state.takes[i];
  const job = state.designJob;
  if (!take || !job) return null;
  if (take.saved) return take.saved;
  const template = state.templates.find((t) => t.id === state.preset);
  const base = template ? template.name : "Custom voice";
  let n = 1;
  const taken = (k: number) => state.voices.some((v) => v.voice_id === `${slug(base)}-v${k}`);
  while (taken(n)) n++;
  const voiceId = `${slug(base)}-v${n}`;
  const name = n > 1 ? `${base} ${n}` : base;
  toast(`Saving ${name}…`);
  try {
    const lock = await api.lockVoice({ voice_id: voiceId, from_design: job.id, candidate: take.index, name });
    const done = await api.waitJob(lock.id);
    if (done.status !== "succeeded") throw new Error(done.error ?? done.status);
    take.saved = voiceId;
    state.voiceId = voiceId;
    state.versionId = null;
    await loadVoices();
    renderTakes();
    toast(`Saved as ${name}.`, { label: "Narrate now", run: () => go("studio", "script") });
    return voiceId;
  } catch (err) {
    fail(err, "Keep failed");
    return null;
  }
}

/* voices */
async function loadVoices() {
  try {
    state.voices = await api.voices();
    if (!state.voiceId || !voiceById(state.voiceId)) state.voiceId = state.voices[0]?.voice_id ?? null;
    renderVoices();
    renderCounts();
    if (state.page === "studio") renderStrip();
  } catch (err) {
    fail(err, "Could not load voices");
  }
}
async function versionsFor(voiceId: string): Promise<Version[]> {
  if (!state.versions[voiceId]) {
    state.versions[voiceId] = await api.versions(voiceId);
  }
  return state.versions[voiceId]!;
}
function renderVoices() {
  const q = $<HTMLInputElement>("voice-search").value.trim().toLowerCase();
  const list = state.voices.filter((v) => !q || `${v.name} ${v.voice_id} ${v.notes ?? ""}`.toLowerCase().includes(q));
  const windowed = pageWindow(list, "voices");
  $("voice-grid").innerHTML =
    windowed.rows
      .map(
        (v) => `
    <article class="card voice-card">
      <div class="row">
        <div class="orb" style="${orbVars(palOf(v.voice_id))}"></div>
        <div class="grow">
          <h3>${esc(v.name)} ${v.favorite ? "★" : ""}</h3>
          <div class="mono muted">${esc(v.voice_id)} · ${esc(v.current_version_id ?? "")}</div>
        </div>
        <button class="play ghost" type="button" data-play-key="voice-${esc(v.voice_id)}" data-voice-play="${esc(v.voice_id)}" aria-label="Play ${esc(v.name)}">${PLAY}</button>
      </div>
      <p>${esc(v.notes ?? "")}</p>
      <div class="row"><span class="chip">${esc(v.language)}</span><span class="chip">${v.version_count ?? 1} version${(v.version_count ?? 1) === 1 ? "" : "s"}</span><button class="chip" type="button" data-fav="${esc(v.voice_id)}" title="Favorite">${v.favorite ? "★ favorite" : "☆ favorite"}</button></div>
      <div class="quick">
        ${state.styles.map((s) => `<button type="button" data-quick="${esc(v.voice_id)}" data-style="${esc(s.id)}">${esc(s.name)}</button>`).join("")}
      </div>
    </article>`,
      )
      .join("") || `<p class="muted">${q ? `No saved voice matches “${esc(q)}”.` : "No voices yet. Keep a take in the Playground."}</p>`;
  $("voice-pager").innerHTML = list.length ? pagerHtml("voices", windowed.page, windowed.pages) : "";
  paintPlayer();
}

/* studio */
function styleById(id: string) {
  return state.styles.find((s) => s.id === id);
}
async function renderStrip() {
  $("voice-strip").innerHTML =
    state.voices
      .map(
        (v) => `
    <button type="button" class="vchip" data-pick="${esc(v.voice_id)}" aria-pressed="${v.voice_id === state.voiceId}">
      <span class="orb" style="${orbVars(palOf(v.voice_id))}"></span>${esc(v.name)}
    </button>`,
      )
      .join("") || `<span class="muted">No voices yet. Keep a take in the Playground first.</span>`;
  $("style-seg").innerHTML = state.styles.map((s) => `<button type="button" data-style-pick="${esc(s.id)}" aria-pressed="${s.id === state.style}">${esc(s.name)}</button>`).join("");
  const style = styleById(state.style);
  $("style-note").textContent = style ? (STYLE_NOTES[style.id] ?? `Temperature ${style.temperature}, pauses ${style.pause_comma_s}/${style.pause_period_s}/${style.pause_paragraph_s} s, ${style.loudness_dbfs} dBFS.`) : "";
  if (state.steadiness === null && style) {
    $<HTMLInputElement>("steadiness").value = String(style.temperature);
    $("steadiness-val").textContent = "style default";
  }
  const sel = $<HTMLSelectElement>("version-pick");
  if (state.voiceId) {
    try {
      const versions = await versionsFor(state.voiceId);
      const voice = voiceById(state.voiceId);
      const chosen = state.versionId && versions.some((v) => v.id === state.versionId) ? state.versionId : (voice?.current_version_id ?? versions[0]?.id ?? null);
      state.versionId = chosen;
      sel.innerHTML = versions.map((v) => `<option value="${esc(v.id)}" ${v.id === chosen ? "selected" : ""}>${esc(v.label)} (${esc(v.id)})</option>`).join("");
    } catch (err) {
      fail(err, "Could not load versions");
    }
  } else sel.innerHTML = "";
}
interface Beat {
  text: string;
  tags: string[];
  pause: number | null;
}
function parseBeats(text: string): Beat[] {
  const beats: Beat[] = [];
  let pending: string[] = [];
  for (const part of text.split(/(\[[^\[\]]+\])/)) {
    if (!part) continue;
    const m = part.match(/^\[([^\[\]]+)\]$/);
    if (m) {
      const tag = m[1]!.trim().toLowerCase();
      const pause = tag.match(/^pause\s+(\d+(?:\.\d+)?)s$/);
      if (pause) {
        if (beats.length) beats[beats.length - 1]!.pause = parseFloat(pause[1]!);
        continue;
      }
      pending.push(tag);
      continue;
    }
    const sentences = part
      .split(/(?<=[.!?])\s+/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (!sentences.length) continue;
    const tags = pending;
    pending = [];
    sentences.forEach((s) => beats.push({ text: s, tags, pause: null }));
  }
  if (pending.length) beats.push({ text: "", tags: pending, pause: null });
  return beats;
}
function renderBeats() {
  const text = $<HTMLTextAreaElement>("script").value;
  const beats = parseBeats(text);
  const words = (text.replace(/\[[^\]]*\]/g, " ").match(/\S+/g) || []).length;
  const seconds = words / 2.5;
  const unknown = [...new Set(beats.flatMap((b) => b.tags))];
  const render = seconds * 3;
  $("est-audio").textContent = fmt(seconds);
  $("est-time").textContent = render < 60 ? `${Math.max(1, Math.round(render))} s` : `${Math.round(render / 60)} min`;
  $("stats").innerHTML = `<span><b>${words}</b> words</span><span><b>${beats.length}</b> beats</span>
    ${unknown.length ? `<span class="chip bad">Unknown tag: ${unknown.map(esc).join(", ")}. The only tag is [pause 0.8s].</span>` : ""}
    ${words > 1500 ? `<span class="chip warn">Over ten minutes. Split into two renders.</span>` : ""}`;
  $("beats-note").textContent = beats.length ? `${beats.length} beats, each cloned from the chosen version` : "";
  const progress = state.renderJob?.progress;
  const doneCount = state.rendering && progress ? progress.completed : state.renderJob?.status === "succeeded" ? beats.length : -1;
  const windowed = pageWindow(beats, "beats");
  $("beats").innerHTML =
    windowed.rows
      .map((b, i) => {
        const n = windowed.start + i;
        const st = doneCount < 0 ? "" : n < doneCount ? "done" : n === doneCount && state.rendering ? "speaking" : "";
        return `<div class="beat ${st} ${b.tags.length ? "bad" : ""}">
      <span class="n">${n + 1}</span>
      <div style="min-width:0">
        <div class="txt">${b.text ? esc(b.text) : `<span class="muted">pause</span>`}</div>
        ${b.tags.length || b.pause ? `<div class="tags">${b.tags.map((t) => `<span class="chip bad">${esc(t)}</span>`).join("")}${b.pause ? `<span class="chip">pause ${b.pause}s</span>` : ""}</div>` : ""}
      </div>
      <span class="st">${st === "speaking" ? "Speaking" : st === "done" ? "Done" : ""}</span>
    </div>`;
      })
      .join("") || `<p class="muted" style="margin:0">Write a script and the beats appear here.</p>`;
  $("beat-pager").innerHTML = beats.length ? pagerHtml("beats", windowed.page, windowed.pages) : "";
  $<HTMLButtonElement>("render").disabled = state.rendering || !beats.length || unknown.length > 0 || !state.voiceId;
}
function insertTag(tag: string) {
  const box = $<HTMLTextAreaElement>("script");
  const text = tag === "pause" ? "[pause 0.8s] " : `[${tag}] `;
  box.setRangeText(text, box.selectionStart, box.selectionEnd, "end");
  box.focus();
  renderBeats();
}
function speakParams() {
  const params: Record<string, number> = {};
  if (state.steadiness !== null) params.temperature = state.steadiness;
  const topp = num("s-topp");
  const topk = num("s-topk");
  const rep = num("s-rep");
  const tokens = num("s-tokens");
  const speed = num("s-speed");
  if (topp) params.top_p = topp;
  if (topk) params.top_k = topk;
  if (rep) params.repetition_penalty = rep;
  if (tokens) params.max_tokens = tokens;
  if (speed && speed !== 1) params.speed = speed;
  return params;
}
async function render() {
  if (state.rendering || !state.voiceId) return;
  const script = $<HTMLTextAreaElement>("script").value.trim();
  const beats = parseBeats(script);
  if (!beats.length || $<HTMLButtonElement>("render").disabled) return;
  const voice = voiceById(state.voiceId);
  const title = $<HTMLInputElement>("nar-title").value.trim() || `${voice?.name ?? state.voiceId} · ${styleById(state.style)?.name ?? state.style}`;
  state.rendering = true;
  state.renderJob = null;
  $("render-chip").className = "chip tag";
  $("render-chip").textContent = "Rendering";
  bar(0, 1);
  renderBeats();
  try {
    const narration = await api.createNarration({
      title,
      voice_id: state.voiceId,
      version_id: state.versionId ?? undefined,
      style_id: state.style,
      script,
      language: voice?.language ?? "English",
      params: speakParams(),
      seed: num("s-seed") ?? 1,
    });
    const job = await api.renderNarration(narration.id);
    state.renderJob = job;
    const done = await api.waitJob(job.id, (j) => {
      state.renderJob = j;
      $("render-detail").textContent = j.progress.detail;
      if (j.progress.total) bar(j.progress.completed, j.progress.total);
      renderBeats();
    });
    if (done.status !== "succeeded") throw new Error(done.error ?? done.status);
    bar(1, 1);
    $("render-chip").className = "chip ok";
    $("render-chip").textContent = "Done";
    $("render-detail").textContent = done.deferred.length ? `Recorded on the beats: ${done.deferred.join(", ")}` : "";
    await loadDownloads();
    const path = `/v1/narrations/${encodeURIComponent(narration.id)}/audio.wav`;
    void play({ key: `nar-${narration.id}`, title, sub: `${voice?.name ?? state.voiceId} · ${styleById(state.style)?.name ?? state.style}`, pal: palOf(state.voiceId), path, downloadName: `${slug(title)}.wav` });
    toast("Narration ready and playing.", { label: "Open downloads", run: () => go("downloads") });
  } catch (err) {
    $("render-chip").className = "chip bad";
    $("render-chip").textContent = "Failed";
    fail(err, "Render failed");
  } finally {
    state.rendering = false;
    renderBeats();
    setTimeout(() => {
      if (!state.rendering) bar(0, 1);
    }, 4000);
  }
}
function bar(done: number, total: number) {
  $("render-bar").style.width = `${Math.min(100, (done / Math.max(1, total)) * 100)}%`;
}

/* downloads */
async function loadDownloads() {
  try {
    state.downloads = await api.downloads();
    renderDownloads();
    renderCounts();
  } catch (err) {
    fail(err, "Could not load downloads");
  }
}
function dlName(d: Download) {
  return d.kind === "voice" ? `${d.version_id?.replace("@", "-v")}.wav` : `${slug(d.title || d.id)}.wav`;
}
function renderDownloads() {
  const rows = state.downloads.filter((d) => state.filter === "all" || d.kind === state.filter);
  const windowed = pageWindow(rows, "downloads");
  $("dl-rows").innerHTML =
    windowed.rows
      .map((d) => {
        const v = voiceById(d.voice_id);
        const pal = palOf(d.voice_id ?? d.id);
        const styleName = d.kind === "voice" ? "Voice master" : d.kind === "speech" ? "Speech" : (styleById(d.style_id ?? "")?.name ?? d.style_id ?? "");
        return `<tr>
      <td><div class="file-cell"><div class="orb" style="${orbVars(pal)}"></div><span class="mono">${esc(dlName(d))}</span></div></td>
      <td>${esc(v ? v.name : (d.voice_id ?? ""))}<div class="muted mono" style="font-size:12px">${esc(d.version_id ?? "")}</div></td>
      <td><span class="chip ${d.kind === "voice" ? "" : "tag"}">${esc(styleName)}</span></td>
      <td>${fmt(d.duration_s ?? 0)}</td>
      <td class="muted">${esc(when(d.created_at))}</td>
      <td><div class="actions-cell">
        <button class="play ghost" type="button" data-play-key="dl-${esc(d.kind)}-${esc(d.id)}" data-dl-play="${esc(d.kind)}:${esc(d.id)}" aria-label="Play">${PLAY}</button>
        <button class="btn sm" type="button" data-dl="${esc(d.kind)}:${esc(d.id)}">${DL} WAV</button>
        <button class="btn sm" type="button" data-path="${esc(d.kind)}:${esc(d.id)}">Copy URL</button>
      </div></td>
    </tr>`;
      })
      .join("") || `<tr><td colspan="6" class="muted">Nothing here yet.</td></tr>`;
  $("download-pager").innerHTML = rows.length ? pagerHtml("downloads", windowed.page, windowed.pages) : "";
  paintPlayer();
}
function findDownload(key: string) {
  const [kind, ...rest] = key.split(":");
  const id = rest.join(":");
  return state.downloads.find((d) => d.kind === kind && d.id === id);
}
function renderCounts() {
  $("count-voices").textContent = String(state.voices.length);
  $("count-downloads").textContent = String(state.downloads.length);
}

/* connect */
async function checkHealth() {
  const origin = location.origin;
  $("api-snippet").textContent = `curl -X POST ${origin}/v1/narrations \\
  -H "Authorization: Bearer $VOICE_TOKEN" -H "Content-Type: application/json" \\
  -d '{"title":"Intro","voice_id":"${state.voiceId ?? "narrator-v1"}","style_id":"narration",
       "script":"The room went quiet. [pause 0.8s] Then the lights came on."}'
# → {"id":"nar_…"}  then:
curl -X POST -H "Authorization: Bearer $VOICE_TOKEN" ${origin}/v1/narrations/NAR_ID/render
curl -H "Authorization: Bearer $VOICE_TOKEN" -o narration.wav ${origin}/v1/narrations/NAR_ID/audio.wav`;
  $("mcp-snippet").textContent = `{
  "mcpServers": {
    "voice-design": {
      "url": "${origin}/mcp",
      "headers": { "Authorization": "Bearer \${VOICE_TOKEN}" }
    }
  }
}`;
  $("tool-chips").innerHTML = ["create_playground", "run_playground", "lock_voice", "create_narration", "render_saved_narration", "download_narration", "list_downloads"].map((t) => `<span class="chip tag">${t}</span>`).join("");
  try {
    state.health = await api.health();
    const h = state.health;
    const ok = h.status === "ok";
    $("top-api-dot").classList.toggle("off", !ok);
    $("foot-engine-dot").classList.toggle("off", !ok);
    $("foot-engine").textContent = `Engine on ${h.backend}`;
    $("api-chip").className = `chip ${ok ? "ok" : "bad"}`;
    $("api-chip").textContent = ok ? "Live" : "Error";
    $("api-text").textContent = ok ? `Engine ${h.version} on ${h.backend} (${h.device}). ${h.queued_jobs} queued.` : (h.error ?? "The engine reported an error.");
    $("design-hint").textContent = h.backend === "fake" ? "Fake backend: instant tones for testing" : `About ${state.takeCount * 20} s for ${state.takeCount} takes`;
  } catch (err) {
    state.health = null;
    $("top-api-dot").classList.add("off");
    $("foot-engine-dot").classList.add("off");
    $("foot-engine").textContent = "Engine unreachable";
    $("api-chip").className = "chip bad";
    $("api-chip").textContent = "Down";
    $("api-text").textContent = err instanceof ApiError && err.status === 401 ? "The server wants a bearer token. Paste it below." : "The engine is not running. Start it with `bun start.ts`.";
  }
  state.mcp = await api.mcpAlive();
  setMcp(state.mcp);
  renderBeats();
}
function setMcp(on: boolean) {
  ["top-mcp-dot", "foot-mcp-dot"].forEach((id) => $(id).classList.toggle("off", !on));
  $("top-mcp").textContent = on ? "MCP" : "MCP down";
  $("foot-mcp").textContent = on ? `MCP on ${location.host}/mcp` : "MCP unavailable";
  $("mcp-chip").className = `chip ${on ? "ok" : "bad"}`;
  $("mcp-chip").textContent = on ? "Live" : "Unavailable";
  $("fallback").classList.toggle("down", !on);
  $("fallback").querySelector(".dot")?.classList.toggle("off", !on);
  $("fallback-text").textContent = on
    ? "MCP and the API share one engine. Anything an agent makes shows up in Downloads, and anything you make here is visible to agents."
    : "MCP is not answering. This dashboard still works because it uses the API. Agents can call the same API with the curl above, or you can hand them a WAV from Downloads.";
}
async function copy(text: string, label: string) {
  try {
    await navigator.clipboard.writeText(text);
    toast(`${label} copied.`);
  } catch {
    toast(`The browser blocked the clipboard. Select and copy the ${label.toLowerCase()} by hand.`);
  }
}

/* events */
document.addEventListener("click", (e) => {
  const t = (e.target as HTMLElement).closest("button") as HTMLButtonElement | null;
  if (!t || t.disabled) return;
  const d = t.dataset;
  if (d.pageFor && d.pageTo && d.pageFor in PAGE_SIZE) {
    const key = d.pageFor as keyof typeof PAGE_SIZE;
    state.listPage[key] = Number(d.pageTo);
    if (key === "presets") renderPresets();
    else if (key === "takes") renderTakes();
    else if (key === "voices") renderVoices();
    else if (key === "downloads") renderDownloads();
    else renderBeats();
    return;
  }
  if (d.go) return go(d.go, d.focus);
  if (d.preset) return applyPreset(d.preset);
  if (d.n) {
    state.takeCount = Number(d.n);
    document.querySelectorAll("#take-count button").forEach((b) => b.setAttribute("aria-pressed", String(b === t)));
    if (state.health?.backend !== "fake") $("design-hint").textContent = `About ${state.takeCount * 20} s for ${state.takeCount} takes`;
    return;
  }
  if (d.take !== undefined && d.playKey) {
    const take = state.takes[Number(d.take)];
    if (!take) return;
    return void play({ key: d.playKey, title: `Take ${Number(d.take) + 1}`, sub: take.saved ? `Saved as ${take.saved}` : "Playground · not saved", pal: Number(d.take), path: take.url, downloadName: take.file });
  }
  if (d.keep !== undefined) return void keep(Number(d.keep));
  if (d.narrate) {
    state.voiceId = d.narrate;
    state.versionId = null;
    return go("studio", "script");
  }
  if (d.voicePlay) {
    const v = voiceById(d.voicePlay);
    if (!v) return;
    return void play({ key: d.playKey!, title: v.name, sub: `${v.voice_id} · ${v.current_version_id ?? "master"}`, pal: palOf(v.voice_id), path: `/v1/voices/${encodeURIComponent(v.voice_id)}/files/master.wav`, downloadName: `${v.voice_id}-master.wav` });
  }
  if (d.versionPlay) {
    const voiceId = state.voiceId;
    if (!voiceId) return;
    return void play({ key: d.playKey!, title: d.versionPlay, sub: `${voiceById(voiceId)?.name ?? voiceId} · version master`, pal: palOf(voiceId), path: `/v1/voices/${encodeURIComponent(voiceId)}/versions/${encodeURIComponent(d.versionPlay)}/master.wav`, downloadName: `${d.versionPlay.replace("@", "-v")}.wav` });
  }
  if (d.fav) {
    const v = voiceById(d.fav);
    if (!v) return;
    return void api
      .updateVoice(v.voice_id, { favorite: !v.favorite })
      .then(loadVoices)
      .catch((err) => fail(err, "Could not update"));
  }
  if (d.quick) {
    state.voiceId = d.quick;
    state.versionId = null;
    state.style = d.style ?? "narration";
    state.steadiness = null;
    return go("studio", "script");
  }
  if (d.pick) {
    state.voiceId = d.pick;
    state.versionId = null;
    void renderStrip();
    return renderBeats();
  }
  if (d.stylePick) {
    state.style = d.stylePick;
    state.steadiness = null;
    void renderStrip();
    return renderBeats();
  }
  if (d.tag) return insertTag(d.tag);
  if (d.f) {
    state.filter = d.f;
    state.listPage.downloads = 0;
    document.querySelectorAll("#dl-filter button").forEach((b) => b.setAttribute("aria-pressed", String(b === t)));
    return renderDownloads();
  }
  if (d.dlPlay) {
    const item = findDownload(d.dlPlay);
    if (!item) return;
    const v = voiceById(item.voice_id);
    return void play({ key: d.playKey!, title: item.title || dlName(item), sub: `${v ? v.name : (item.voice_id ?? "")} · ${item.kind}`, pal: palOf(item.voice_id ?? item.id), path: item.url, downloadName: dlName(item) });
  }
  if (d.dl) {
    const item = findDownload(d.dl);
    if (item) void downloadFile(item.url, dlName(item));
    return;
  }
  if (d.path) {
    const item = findDownload(d.path);
    if (item) void copy(`${location.origin}${item.url}`, "Download URL");
    return;
  }
  if (d.copy) return void copy($(d.copy).textContent ?? "", d.copy === "api-snippet" ? "API example" : "MCP config");
});

$("design-form").addEventListener("submit", (e) => {
  e.preventDefault();
  void generate();
});
$("playground-pick").addEventListener("change", () => {
  const id = $<HTMLSelectElement>("playground-pick").value;
  state.playgroundId = id || null;
  state.takes = [];
  state.designJob = null;
  if (!id) return renderTakes();
  void api
    .playground(id)
    .then((pg) => {
      const c = pg.config as Record<string, any>;
      $<HTMLTextAreaElement>("instruct").value = String(c.instruct ?? "");
      $<HTMLTextAreaElement>("sample").value = String(c.text ?? "");
      if (c.language) $<HTMLSelectElement>("language").value = String(c.language);
      if (c.seed_start) $<HTMLInputElement>("seed").value = String(c.seed_start);
      if (c.params?.temperature) $<HTMLInputElement>("d-temp").value = String(c.params.temperature);
      state.preset = pg.template_id;
      renderPresets();
      const last = [...pg.runs].reverse().find((r) => r.job?.status === "succeeded");
      if (last?.job) {
        state.designJob = last.job;
        state.takes = last.job.outputs.map((o, i) => ({
          index: i + 1,
          file: o.file,
          url: o.url ?? `/v1/jobs/${last.job!.id}/files/${o.file}`,
          seed: o.seed,
          seconds: o.checks.duration_s,
          ok: o.checks.ok,
          warnings: o.checks.warnings,
          saved: state.voices.find((v) => v.from_job === last.job!.id && v.candidate === i + 1)?.voice_id ?? null,
        }));
      }
      renderTakes();
    })
    .catch((err) => fail(err, "Could not open playground"));
});
$("instruct").addEventListener("input", () => {
  const match = state.templates.find((t) => t.instruct === $<HTMLTextAreaElement>("instruct").value.trim());
  state.preset = match ? match.id : null;
  renderPresets();
});
$("steadiness").addEventListener("input", (e) => {
  state.steadiness = Number((e.target as HTMLInputElement).value);
  $("steadiness-val").textContent = state.steadiness.toFixed(2);
});
$("version-pick").addEventListener("change", () => {
  state.versionId = $<HTMLSelectElement>("version-pick").value || null;
});
$("script").addEventListener("input", renderBeats);
$("render").addEventListener("click", () => void render());
$("voice-search").addEventListener("input", () => {
  state.listPage.voices = 0;
  renderVoices();
});
$("open-design-settings").addEventListener("click", () => $<HTMLDialogElement>("design-settings").showModal());
$("open-speak-settings").addEventListener("click", () => $<HTMLDialogElement>("speak-settings").showModal());
$("dl-refresh").addEventListener("click", () => void loadDownloads());
$("token-save").addEventListener("click", () => {
  saveToken($<HTMLInputElement>("token").value.trim());
  blobCache.clear();
  toast("Token saved.");
  void boot(false);
});
$("p-play").addEventListener("click", () => {
  if (!state.current) {
    const d = state.downloads[0];
    if (!d) return toast("Nothing to play yet.");
    return void play({ key: `dl-${d.kind}-${d.id}`, title: d.title || dlName(d), sub: d.kind, pal: palOf(d.voice_id ?? d.id), path: d.url, downloadName: dlName(d) });
  }
  if (playing()) audio.pause();
  else void audio.play().catch(() => undefined);
});
$("p-bar").addEventListener("click", (e) => {
  if (!state.current || !audio.duration) return;
  const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
  audio.currentTime = ((e.clientX - r.left) / r.width) * audio.duration;
  paintPlayer();
});
$("p-download").addEventListener("click", () => {
  if (!state.current) return toast("Play something first.");
  void downloadFile(state.current.path, state.current.downloadName);
});
$("theme").addEventListener("click", () => {
  const root = document.documentElement;
  root.dataset.theme = root.dataset.theme === "dark" ? "light" : "dark";
  localStorage.setItem("voice-design.theme", root.dataset.theme);
});
function setSidebar(collapsed: boolean) {
  $("app").classList.toggle("collapsed", collapsed);
  const toggle = $("side-toggle");
  toggle.setAttribute("aria-expanded", String(!collapsed));
  toggle.setAttribute("aria-label", collapsed ? "Expand the sidebar" : "Collapse the sidebar");
  toggle.title = collapsed ? "Expand the sidebar" : "Collapse the sidebar";
  localStorage.setItem("voice-design.sidebar", collapsed ? "collapsed" : "open");
}
$("side-toggle").addEventListener("click", () => setSidebar(!$("app").classList.contains("collapsed")));
document.addEventListener("keydown", (e) => {
  const typing = /^(INPUT|TEXTAREA|SELECT)$/.test((document.activeElement as HTMLElement)?.tagName ?? "");
  if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
    e.preventDefault();
    if (state.page === "playground") void generate();
    if (state.page === "studio") void render();
    return;
  }
  if (typing) return;
  if (e.key === " ") {
    e.preventDefault();
    if (state.current) {
      if (playing()) audio.pause();
      else void audio.play().catch(() => undefined);
      return;
    }
    const first = state.takes[0];
    if (state.page === "playground" && first) {
      void play({ key: "take-0", title: "Take 1", sub: "Playground · not saved", pal: 0, path: first.url, downloadName: first.file });
    } else $("p-play").click();
    return;
  }
  const n = Number(e.key);
  if (n >= 1 && n <= ORDER.length) go(ORDER[n - 1]!);
});

/* boot */
async function boot(first: boolean) {
  $<HTMLInputElement>("token").value = loadToken();
  await checkHealth();
  if (!state.health) {
    renderTakes();
    renderBeats();
    return;
  }
  try {
    const [templates, voices, styles, playgrounds, downloads] = await Promise.all([api.templates(), api.voices(), api.styles(), api.playgrounds(), api.downloads()]);
    state.templates = templates;
    state.voices = voices;
    state.styles = styles;
    state.playgrounds = playgrounds.map((p) => ({ id: p.id, name: p.name }));
    state.downloads = downloads;
    if (!state.voiceId) state.voiceId = voices[0]?.voice_id ?? null;
    if (!styles.some((s) => s.id === state.style)) state.style = styles[0]?.id ?? "narration";
  } catch (err) {
    fail(err, "Could not load the library");
  }
  renderPresets();
  if (first && state.templates[0] && !$<HTMLTextAreaElement>("instruct").value) applyPreset(state.templates[0].id);
  renderPlaygroundPick();
  renderTakes();
  renderVoices();
  renderDownloads();
  renderCounts();
  void renderStrip();
  renderBeats();
}

/* sync: the dashboard follows the database, so work done by an agent over MCP
   shows up here within a few seconds, and nothing is re-rendered when nothing changed. */
let syncing = false;
async function syncLibrary() {
  if (!state.health || syncing || document.hidden) return;
  syncing = true;
  try {
    const [templates, voices, styles, playgrounds, downloads] = await Promise.all([api.templates(), api.voices(), api.styles(), api.playgrounds(), api.downloads()]);
    const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);
    if (!same(templates, state.templates)) {
      state.templates = templates;
      renderPresets();
    }
    const nextPlaygrounds = playgrounds.map((p) => ({ id: p.id, name: p.name }));
    if (!same(nextPlaygrounds, state.playgrounds)) {
      state.playgrounds = nextPlaygrounds;
      renderPlaygroundPick();
    }
    const stylesChanged = !same(styles, state.styles);
    if (stylesChanged) {
      state.styles = styles;
      if (!styles.some((s) => s.id === state.style)) state.style = styles[0]?.id ?? "narration";
    }
    const voicesChanged = !same(voices, state.voices);
    if (voicesChanged) {
      state.voices = voices;
      state.versions = {};
      if (!state.voiceId || !voiceById(state.voiceId)) state.voiceId = voices[0]?.voice_id ?? null;
    }
    if (voicesChanged || stylesChanged) {
      renderVoices();
      if (state.page === "studio") {
        void renderStrip();
        renderBeats();
      }
    }
    if (!same(downloads, state.downloads)) {
      state.downloads = downloads;
      renderDownloads();
    }
    if (voicesChanged || !same(downloads, state.downloads)) renderCounts();
  } catch {
    // The health check reports an unreachable engine; a missed sync is retried on the next tick.
  } finally {
    syncing = false;
  }
}

document.documentElement.dataset.theme = localStorage.getItem("voice-design.theme") ?? (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
setSidebar(localStorage.getItem("voice-design.sidebar") === "collapsed");
$("tagbar").innerHTML = `<button type="button" data-tag="pause">[pause 0.8s]</button>`;
$<HTMLTextAreaElement>("script").value = `The room went quiet. Nobody wanted to be the first to speak.

Then someone at the back started it, and the whole row followed.
[pause 0.8s]
Don't look now. He's still watching.

And that was the moment the experiment finally worked.`;
const start = location.hash.slice(1);
go(PAGES[start] ? start : "playground");
void boot(true);
setInterval(() => void checkHealth(), 30000);
setInterval(() => void syncLibrary(), 8000);
addEventListener("focus", () => void syncLibrary());
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) void syncLibrary();
});
