import { useEffect, useMemo, useRef, useState } from "react";
import { ACTIVE, type Api, type DesignSpec, type GenParams, type Job, type Output, type VoiceTemplate } from "./api";
import { errorMessage, ChecksBadges, Field, fmtDate, LANGUAGES, ParamFields, shorten, StatusBadge } from "./common";
import { SoundClip } from "./SoundClip";
import { PALETTES, paletteFor } from "./sound";
import { TemplateCards } from "./TemplateCards";

const DEFAULT_INSTRUCT =
  "An adult male narrator in his mid-thirties with a warm, low-mid voice. Neutral international English, clear diction, calm and curious, like a science explainer who enjoys the topic.";
const DEFAULT_TEXT = "Give it a second. Ordinary things get interesting when they refuse to behave the way we expect.";
const VOICE_ID = /^[a-z0-9][a-z0-9-]{1,62}$/;
const COUNTS = [2, 3, 4, 5, 6, 7, 8];

export function DesignView({
  api,
  jobs,
  onSubmitted,
  onLocked,
  onOpenTemplates,
  pendingTemplate,
  onPendingUsed,
  favoriteIds,
  onAddFavorite,
}: {
  api: Api;
  jobs: Job[];
  onSubmitted: () => void;
  onLocked: (voiceId: string) => void;
  onOpenTemplates: () => void;
  pendingTemplate: VoiceTemplate | null;
  onPendingUsed: () => void;
  favoriteIds: Set<string>;
  onAddFavorite: (voiceId: string) => void;
}) {
  const [instruct, setInstruct] = useState(DEFAULT_INSTRUCT);
  const [text, setText] = useState(DEFAULT_TEXT);
  const [language, setLanguage] = useState("English");
  const [candidates, setCandidates] = useState(4);
  const [seedStart, setSeedStart] = useState(1000);
  const [params, setParams] = useState<GenParams>({});
  const [templates, setTemplates] = useState<VoiceTemplate[]>([]);
  const [loadedId, setLoadedId] = useState<string | null>(null);
  const [templateName, setTemplateName] = useState("");
  const [templateRole, setTemplateRole] = useState("");
  const [savingTemplate, setSavingTemplate] = useState(false);
  const [templateNote, setTemplateNote] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [chosen, setChosen] = useState(1);
  const [playingIndex, setPlayingIndex] = useState<number | null>(null);
  const applied = useRef(false);
  const loaded = templates.find((item) => item.id === loadedId) ?? null;

  function applyTemplate(template: VoiceTemplate) {
    setInstruct(template.instruct);
    setText(template.text);
    setLanguage(template.language);
    setCandidates(template.candidates);
    setSeedStart(template.seed_start);
    setParams(template.params ?? {});
    setLoadedId(template.id);
    setTemplateName(template.origin === "user" ? template.name : "");
    setTemplateRole(template.role);
    setTemplateNote(null);
    document.getElementById("describe-title")?.scrollIntoView({ block: "start" });
  }

  useEffect(() => {
    let alive = true;
    api
      .templates()
      .then((rows) => {
        if (!alive) return;
        setTemplates(rows);
        if (!applied.current && !pendingTemplate && rows[0]) {
          applied.current = true;
          setInstruct(rows[0].instruct);
          setText(rows[0].text);
          setLanguage(rows[0].language);
          setCandidates(rows[0].candidates);
          setSeedStart(rows[0].seed_start);
          setParams(rows[0].params ?? {});
          setLoadedId(rows[0].id);
          setTemplateRole(rows[0].role);
        }
      })
      .catch((err) => alive && setError(errorMessage(err)));
    return () => {
      alive = false;
    };
  }, [api, pendingTemplate]);

  useEffect(() => {
    if (!pendingTemplate) return;
    applied.current = true;
    applyTemplate(pendingTemplate);
    onPendingUsed();
  }, [pendingTemplate, onPendingUsed]);

  const designJobs = useMemo(() => jobs.filter((j) => j.type === "design"), [jobs]);
  const selected = selectedId ? (designJobs.find((j) => j.id === selectedId) ?? null) : (designJobs[0] ?? null);
  const pending = selectedId !== null && selected === null;

  useEffect(() => {
    if (!selectedId && designJobs[0]) setSelectedId(designJobs[0].id);
  }, [designJobs, selectedId]);

  useEffect(() => {
    setChosen(1);
    setPlayingIndex(null);
  }, [selected?.id]);

  async function submit() {
    setError(null);
    setSubmitting(true);
    try {
      const spec: DesignSpec = { type: "design", instruct: instruct.trim(), text: text.trim(), language, candidates, seed_start: seedStart, params };
      const job = await api.submit(spec);
      setSelectedId(job.id);
      onSubmitted();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  async function saveTemplate(mode: "new" | "update") {
    const name = templateName.trim();
    const role = templateRole.trim() || instruct.trim().slice(0, 80);
    if (!name || !role || !instruct.trim() || !text.trim()) {
      setTemplateNote("Name the template, and keep a description and a preview script.");
      return;
    }
    setSavingTemplate(true);
    setTemplateNote(null);
    const body = {
      name,
      role,
      instruct: instruct.trim(),
      text: text.trim(),
      language,
      candidates,
      seed_start: seedStart,
      params,
    };
    const take = selected && chosenOutput ? { from_job: selected.id, candidate: chosen } : {};
    try {
      if (mode === "update" && loaded?.origin === "user") {
        await api.updateTemplate(loaded.id, body);
        if ("from_job" in take && take.from_job) await api.replaceTemplateSample(loaded.id, take.from_job, take.candidate!);
        setTemplateNote("Template updated.");
      } else {
        const created = await api.createTemplate({ ...body, ...take });
        setLoadedId(created.id);
        setTemplateName(created.name);
        setTemplateNote("Template saved.");
      }
      setTemplates(await api.templates());
    } catch (err) {
      setTemplateNote(errorMessage(err));
    } finally {
      setSavingTemplate(false);
    }
  }

  function reuse(job: Job) {
    const spec = job.spec as Partial<DesignSpec>;
    if (spec.instruct) setInstruct(spec.instruct);
    if (spec.text) setText(spec.text);
    if (spec.language) setLanguage(spec.language);
    if (spec.candidates) setCandidates(spec.candidates);
    if (spec.seed_start != null) setSeedStart(spec.seed_start);
    setParams(spec.params ?? {});
  }

  const ready = selected?.outputs.length ?? 0;
  const wanted = Number(selected?.spec.candidates ?? 0);
  const active = selected ? ACTIVE.has(selected.status) : false;
  const chosenOutput = selected?.outputs[chosen - 1] ?? null;

  return (
    <section className="view" aria-label="Create a voice">
      <div className="hero">
        <div className="hero-copy">
          <span className="eyebrow">Your voice studio / 01</span>
          <h1>
            Give your ideas <em>a voice.</em>
          </h1>
          <p className="lead">Describe a speaker, hear a few possibilities, and keep the one that feels right. Your next great voice starts with a sentence.</p>
          <ol className="steps" aria-label="Voice creation steps">
            <li className="step active">
              <b>1</b> Describe
            </li>
            <li className="step-line" aria-hidden="true" />
            <li className={ready ? "step active" : "step"}>
              <b>2</b> Explore
            </li>
            <li className="step-line" aria-hidden="true" />
            <li className="step">
              <b>3</b> Save and speak
            </li>
          </ol>
        </div>
        <div className="hero-art" aria-hidden="true">
          <svg viewBox="0 0 360 120" fill="none" stroke="white" strokeLinecap="round">
            <path
              d="M0 60h18m7-17v34m9-50v66m10-42v18m10-32v46m10-63v80m10-90v100m10-74v48m10-35v22m10-57v92m10-73v54m10-41v28m10-68v108m10-78v48m10-58v68m10-43v38m10-84v96m10-65v34m10-48v62m10-84v108m10-64v28m10-42v54m10-75v94m10-52v14m10-36v59m10-42v25m10-48v72m10-37v3m10-22v42m10-30v18m10-5h16"
              strokeWidth="5"
              opacity=".88"
            />
          </svg>
        </div>
      </div>
      <section className="template-gallery" aria-labelledby="template-gallery-title">
        <div className="panel-heading">
          <div>
            <h2 id="template-gallery-title">Templates</h2>
            <p>Play a sample before you generate. Loading one fills the form.</p>
          </div>
          <button type="button" className="secondary" onClick={onOpenTemplates}>
            See all
          </button>
        </div>
        {templates.length === 0 ? (
          <p className="muted small">Loading templates…</p>
        ) : (
          <TemplateCards api={api} templates={templates} layout="row" loadedId={loadedId} onLoad={applyTemplate} />
        )}
      </section>
      <div className="workspace">
        <section className="panel pad" aria-labelledby="describe-title">
          <div className="panel-heading">
            <div>
              <h2 id="describe-title">Describe your voice</h2>
              <p>Paint the personality. The model handles the sound.</p>
            </div>
            <span className="tiny-tag">Step 1</span>
          </div>
          <Field label="Voice description" hint="Age, tone, accent, energy">
            <textarea className="description" value={instruct} onChange={(e) => setInstruct(e.target.value)} maxLength={2000} />
          </Field>
          <Field label="Preview script" hint="Every candidate reads this">
            <textarea value={text} onChange={(e) => setText(e.target.value)} maxLength={1000} />
          </Field>
          <div className="form-row">
            <Field label="Language">
              <select value={language} onChange={(e) => setLanguage(e.target.value)}>
                {LANGUAGES.map((item) => (
                  <option key={item}>{item}</option>
                ))}
              </select>
            </Field>
            <Field label="Candidates">
              <select value={candidates} onChange={(e) => setCandidates(Number(e.target.value))}>
                {COUNTS.map((count) => (
                  <option key={count} value={count}>
                    {count} voices
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <ParamFields
            value={params}
            onChange={setParams}
            showSpeed={false}
              extra={
                <Field label="First seed" hint="Candidate n uses seed + n − 1">
                  <div className="row">
                    <input type="number" min={0} value={seedStart} onChange={(e) => setSeedStart(Number(e.target.value))} />
                    <button type="button" className="secondary" onClick={() => setSeedStart((value) => value + candidates)}>
                      New seed
                    </button>
                  </div>
                </Field>
              }
          />
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          <button className="primary full" type="button" onClick={() => void submit()} disabled={submitting || !instruct.trim() || !text.trim()}>
            {submitting ? "Submitting…" : "✦  Generate voice previews"}
          </button>
          <div className="template-save">
            <Field label="Template name">
              <input value={templateName} onChange={(e) => setTemplateName(e.target.value)} maxLength={80} placeholder="Name this recipe" aria-label="Template name" />
            </Field>
            <Field label="Card line">
              <input value={templateRole} onChange={(e) => setTemplateRole(e.target.value)} maxLength={120} placeholder="Short line for the gallery" aria-label="Template card line" />
            </Field>
            <div className="row">
              {loaded?.origin === "user" ? (
                <>
                  <button type="button" className="secondary" disabled={savingTemplate} onClick={() => void saveTemplate("update")}>
                    Update template
                  </button>
                  <button type="button" className="secondary" disabled={savingTemplate} onClick={() => void saveTemplate("new")}>
                    Save as new
                  </button>
                </>
              ) : (
                <button type="button" className="secondary" disabled={savingTemplate} onClick={() => void saveTemplate("new")}>
                  {savingTemplate ? "Saving…" : "Save template"}
                </button>
              )}
            </div>
            <p className="muted small">{chosenOutput ? "The selected take is stored as the sample." : "Generate a take first if you want this template to have a sample."}</p>
            {templateNote && <p className="muted small">{templateNote}</p>}
          </div>
        </section>
        <section className="panel results" aria-labelledby="results-title" aria-busy={active || pending}>
          <div className="panel-heading">
            <div>
              <h2 id="results-title">Explore your voices</h2>
              <p>Same words, different speakers. Listen and choose.</p>
            </div>
            <div className="panel-actions">
              {selected && (active ? <StatusBadge status={selected.status} /> : <span className="tiny-tag">{ready} ready</span>)}
            </div>
          </div>
          {designJobs.length > 0 && (
            <div className="history">
              <select aria-label="Previous designs" value={selected?.id ?? ""} onChange={(e) => setSelectedId(e.target.value)}>
                {designJobs.map((job) => (
                  <option key={job.id} value={job.id}>
                    {fmtDate(job.created_at)} · {shorten(String(job.spec.instruct ?? ""), 56)}
                  </option>
                ))}
              </select>
              {selected && (
                <button type="button" className="secondary" onClick={() => reuse(selected)}>
                  Copy settings
                </button>
              )}
            </div>
          )}
          {pending && (
            <p className="muted small" role="status">
              Sending to the engine…
            </p>
          )}
          {!selected && !pending && <p className="muted empty">Describe a voice and generate previews. They will appear here.</p>}
          {selected && (
            <>
              <p className="prompt-echo">
                <strong>Prompt</strong> {String(selected.spec.instruct ?? "")}
              </p>
              <p className="prompt-echo">
                <strong>Script</strong> {String(selected.spec.text ?? "")}
              </p>
              {active && (
                <p className="muted small" role="status">
                  {selected.status === "queued" ? "Waiting for the engine." : `Generating ${ready} of ${wanted}.`}
                </p>
              )}
              {active && <div className="progress" />}
              {selected.error && (
                <p className="error" role="alert">
                  {selected.error}
                </p>
              )}
              {selected.deferred.length > 0 && <p className="muted small">Ignored by this backend: {selected.deferred.join(", ")}</p>}
              <div className="candidate-grid">
                {selected.outputs.map((output, index) => (
                  <CandidateCard
                    key={`${selected.id}-${output.file}`}
                    api={api}
                    job={selected}
                    output={output}
                    index={index + 1}
                    jobs={jobs}
                    selected={chosen === index + 1}
                    playing={playingIndex === index + 1}
                    onSelect={() => setChosen(index + 1)}
                    onPlaying={(value) => setPlayingIndex((current) => (value ? index + 1 : current === index + 1 ? null : current))}
                  />
                ))}
                {active &&
                  Array.from({ length: Math.max(0, wanted - ready) }, (_, i) => (
                    <article key={`waiting-${i}`} className="candidate waiting" aria-hidden="true">
                      <h3>Candidate {ready + i + 1}</h3>
                      <div className="wave-skeleton" />
                    </article>
                  ))}
              </div>
              {chosenOutput && (
                <SaveRow
                  api={api}
                  job={selected}
                  index={chosen}
                  jobs={jobs}
                  onLocked={onLocked}
                  saved={favoriteIds.has(String(lockFor(jobs, selected, chosen)?.voice_id ?? ""))}
                  onAddFavorite={onAddFavorite}
                />
              )}
            </>
          )}
        </section>
      </div>
    </section>
  );
}

function lockFor(jobs: Job[], job: Job, index: number) {
  return jobs.find((item) => item.type === "lock" && item.spec.from_job === job.id && item.spec.candidate === index && item.status !== "cancelled");
}

function CandidateCard({
  api,
  job,
  output,
  index,
  jobs,
  selected,
  playing,
  onSelect,
  onPlaying,
}: {
  api: Api;
  job: Job;
  output: Output;
  index: number;
  jobs: Job[];
  selected: boolean;
  playing: boolean;
  onSelect: () => void;
  onPlaying: (playing: boolean) => void;
}) {
  const theme = PALETTES[paletteFor(output.seed)];
  const lockJob = lockFor(jobs, job, index);
  const classes = ["candidate", selected && "selected", playing && "playing"].filter(Boolean).join(" ");

  return (
    <article className={classes} aria-label={`Candidate ${index}${selected ? ", selected" : ""}${playing ? ", playing" : ""}`}>
      <div className="candidate-top">
        <div>
          <h3>Candidate {index}</h3>
          <span className="candidate-note">
            {output.checks.duration_s.toFixed(1)} s{playing ? " · playing" : ""}
          </span>
        </div>
        <div className="candidate-labels">
          <span className="vibe" style={{ color: theme.text, background: theme.soft }}>
            {theme.label}
          </span>
          <span className="candidate-id">{String(index).padStart(2, "0")}</span>
        </div>
      </div>
      <SoundClip
        api={api}
        path={output.url ?? `/v1/jobs/${job.id}/files/${output.file}`}
        filename={`${job.id}-${output.file}`}
        label={`candidate ${index}`}
        seed={output.seed}
        onPlayingChange={onPlaying}
      />
      <div className="candidate-foot">
        {output.checks.ok ? <span className="quality">Audio check passed</span> : <ChecksBadges checks={output.checks} warningsOnly />}
        {lockJob ? (
          <span className="saved-as">
            <StatusBadge status={lockJob.status} /> <code>{String(lockJob.spec.voice_id)}</code>
          </span>
        ) : (
          <button type="button" className="select" aria-pressed={selected} onClick={onSelect}>
            {selected ? "Selected ✓" : "Select voice →"}
          </button>
        )}
      </div>
      <details className="tech">
        <summary>Details</summary>
        <p>seed {output.seed ?? "none"}</p>
        <ChecksBadges checks={output.checks} />
      </details>
    </article>
  );
}

function SaveRow({
  api,
  job,
  index,
  jobs,
  onLocked,
  saved,
  onAddFavorite,
}: {
  api: Api;
  job: Job;
  index: number;
  jobs: Job[];
  onLocked: (voiceId: string) => void;
  saved: boolean;
  onAddFavorite: (voiceId: string) => void;
}) {
  const [voiceId, setVoiceId] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const lockJob = lockFor(jobs, job, index);
  const invalid = voiceId.length > 0 && !VOICE_ID.test(voiceId);

  useEffect(() => {
    setError(null);
  }, [index]);

  async function lock() {
    setError(null);
    if (!VOICE_ID.test(voiceId)) {
      setError("Use 2–63 lowercase letters, digits, and dashes, such as narrator-v1.");
      return;
    }
    setBusy(true);
    try {
      await api.submit({ type: "lock", voice_id: voiceId, from_job: job.id, candidate: index, name: name.trim() || undefined });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  if (lockJob) {
    const done = lockJob.status === "succeeded" && lockJob.voice_id;
    return (
      <div className="save-row" role="status">
        <div>
          <strong>
            Candidate {String(index).padStart(2, "0")} {done ? "is saved" : lockJob.status === "failed" ? "could not be saved" : "is being saved"}
          </strong>
          <span>
            Voice id <code>{String(lockJob.spec.voice_id)}</code>
            {lockJob.error ? ` · ${lockJob.error}` : ""}
          </span>
        </div>
        {done && (
          <div className="row">
            {!saved && lockJob.voice_id && (
              <button type="button" className="secondary" onClick={() => onAddFavorite(lockJob.voice_id!)}>
                Add to profile
              </button>
            )}
            <button type="button" className="primary" onClick={() => onLocked(lockJob.voice_id!)}>
              Make speech →
            </button>
          </div>
        )}
      </div>
    );
  }

  return (
    <form
      className="save-row"
      onSubmit={(event) => {
        event.preventDefault();
        void lock();
      }}
    >
      <div>
        <strong>Candidate {String(index).padStart(2, "0")} is selected</strong>
        <span>Keep this voice to use it across future scripts.</span>
      </div>
      <div className="save-fields">
        <input
          value={voiceId}
          onChange={(e) => setVoiceId(e.target.value.toLowerCase())}
          placeholder="voice id, e.g. narrator-v1"
          aria-label="Voice id"
          aria-invalid={invalid}
          aria-describedby="voice-id-help"
        />
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Display name (optional)" aria-label="Display name" />
        <button type="submit" className="primary" disabled={busy || !voiceId}>
          {busy ? "Saving…" : "Save this voice →"}
        </button>
      </div>
      <span id="voice-id-help" className={invalid || error ? "field-error" : "sr"}>
        {error ?? (invalid ? "Use lowercase letters, digits, and dashes." : "Voice ids use lowercase letters, digits, and dashes.")}
      </span>
    </form>
  );
}
