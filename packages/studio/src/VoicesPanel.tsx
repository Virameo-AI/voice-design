import { useEffect, useMemo, useState } from "react";
import { ACTIVE, type Api, type GenParams, type Job, type Voice } from "./api";
import { ChecksBadges, errorMessage, Field, fmtDate, LANGUAGES, ParamFields, secondsBetween, StatusBadge } from "./common";
import { SoundClip } from "./SoundClip";

const DEFAULT_LINE = "What actually happens inside a combustion engine? Let's slow it down and look.";

export function VoicesView({
  api,
  voices,
  jobs,
  selectedVoiceId,
  onSelectVoice,
  onSubmitted,
  favoriteIds,
  onToggleFavorite,
}: {
  api: Api;
  voices: Voice[];
  jobs: Job[];
  selectedVoiceId: string | null;
  onSelectVoice: (id: string) => void;
  onSubmitted: () => void;
  favoriteIds: Set<string>;
  onToggleFavorite: (voiceId: string, add: boolean) => void;
}) {
  const voice = voices.find((item) => item.voice_id === selectedVoiceId) ?? voices[0] ?? null;
  const [text, setText] = useState(DEFAULT_LINE);
  const [language, setLanguage] = useState("English");
  const [seed, setSeed] = useState(1);
  const [params, setParams] = useState<GenParams>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [instruct, setInstruct] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedVoiceId && voices[0]) onSelectVoice(voices[0].voice_id);
  }, [voices, selectedVoiceId, onSelectVoice]);

  useEffect(() => {
    if (voice) setLanguage(voice.language || "English");
  }, [voice?.voice_id, voice?.language]);

  useEffect(() => {
    if (!voice) return;
    let alive = true;
    setInstruct(null);
    api
      .blob(api.voiceFilePath(voice.voice_id, "instruct.txt"))
      .then((blob) => blob.text())
      .then((value) => alive && setInstruct(value.trim()))
      .catch(() => alive && setInstruct(null));
    return () => {
      alive = false;
    };
  }, [api, voice?.voice_id]);

  const takes = useMemo(() => (voice ? jobs.filter((job) => job.type === "speak" && job.spec.voice_id === voice.voice_id) : []), [jobs, voice]);

  async function speak() {
    if (!voice) return;
    setError(null);
    setBusy(true);
    try {
      await api.submit({ type: "speak", voice_id: voice.voice_id, text: text.trim(), language, seed, params });
      onSubmitted();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  function reuse(job: Job) {
    const spec = job.spec as { text?: string; language?: string; seed?: number; params?: GenParams };
    if (spec.text) setText(spec.text);
    if (spec.language) setLanguage(spec.language);
    if (spec.seed != null) setSeed(spec.seed);
    setParams(spec.params ?? {});
  }

  return (
    <section className="view" aria-label="My voices">
      <div className="subhero">
        <span className="eyebrow">Your voice studio / 02</span>
        <h1>
          Your voices, <em>ready to speak.</em>
        </h1>
        <p className="lead">Choose a voice, write the next line, and make a take.</p>
      </div>
      {voices.length === 0 ? (
        <section className="panel pad">
          <p className="muted empty">No voices yet. Create candidates, then save one.</p>
        </section>
      ) : (
        <div className="library">
          <section className="panel voice-list" aria-label="Saved voices">
            <h2>Saved voices</h2>
            {voices.map((item) => (
              <button
                key={item.voice_id}
                type="button"
                className="voice-option"
                aria-selected={item.voice_id === voice?.voice_id}
                onClick={() => onSelectVoice(item.voice_id)}
              >
                <strong>{item.name}</strong>
                <span>
                  {item.language} · {fmtDate(item.created_at)}
                </span>
              </button>
            ))}
          </section>
          {voice && (
            <div className="voice-content">
              <section className="panel pad voice-reference">
                <div className="panel-heading">
                  <div>
                    <h2>{voice.name}</h2>
                    <p>{instruct || voice.notes || voice.voice_id}</p>
                  </div>
                  <div className="panel-actions">
                    <span className="tiny-tag">Saved voice</span>
                    {favoriteIds.has(voice.voice_id) ? (
                      <button type="button" className="secondary" onClick={() => onToggleFavorite(voice.voice_id, false)}>
                        Remove from profile
                      </button>
                    ) : (
                      <button type="button" className="secondary" onClick={() => onToggleFavorite(voice.voice_id, true)}>
                        Add to profile
                      </button>
                    )}
                  </div>
                </div>
                <div className="large-wave">
                  <SoundClip api={api} path={api.voiceFilePath(voice.voice_id, "master.wav")} filename={`${voice.voice_id}-master.wav`} label={`${voice.name} reference clip`} seed={voice.seed} />
                </div>
                <p className="muted small">
                  Voice id <code>{voice.voice_id}</code> · {voice.language} · seed {voice.seed ?? "none"}
                </p>
              </section>
              <section className="panel pad">
                <h2>Make speech</h2>
                <p className="lead">Write naturally. One paragraph per line.</p>
                <Field label="Your script">
                  <textarea className="script" value={text} onChange={(e) => setText(e.target.value)} maxLength={5000} />
                </Field>
                <div className="form-row">
                  <Field label="Language">
                    <select value={language} onChange={(e) => setLanguage(e.target.value)}>
                      {LANGUAGES.map((item) => (
                        <option key={item}>{item}</option>
                      ))}
                    </select>
                  </Field>
                  <Field label="Seed">
                    <div className="row">
                      <input type="number" min={0} value={seed} onChange={(e) => setSeed(Number(e.target.value))} />
                      <button type="button" className="secondary" onClick={() => setSeed((value) => value + 1)}>
                        Next take
                      </button>
                    </div>
                  </Field>
                </div>
                <ParamFields value={params} onChange={setParams} showSpeed />
                {error && <p className="error">{error}</p>}
                <button type="button" className="primary full" onClick={() => void speak()} disabled={busy || !text.trim()}>
                  {busy ? "Submitting…" : "Generate speech"}
                </button>
              </section>
              <section className="panel pad">
                <div className="panel-heading">
                  <div>
                    <h2>Recent takes</h2>
                    <p>Newest lines with this voice.</p>
                  </div>
                  <span className="tiny-tag">{takes.length}</span>
                </div>
                {takes.length === 0 && <p className="muted empty">Nothing generated with this voice yet.</p>}
                {takes.map((job, index) => (
                  <article key={job.id} className="take">
                    <div className="row between wrap">
                      <h3>
                        Take {String(takes.length - index).padStart(2, "0")} · {fmtDate(job.created_at)}
                      </h3>
                      <div className="row wrap">
                        {job.status !== "succeeded" && <StatusBadge status={job.status} />}
                        <button type="button" className="secondary" onClick={() => reuse(job)}>
                          Reuse
                        </button>
                      </div>
                    </div>
                    <p>{String(job.spec.text ?? "")}</p>
                    <p className="muted small">
                      seed {String(job.spec.seed)}
                      {job.finished_at ? ` · took ${secondsBetween(job.started_at, job.finished_at)}` : ""}
                    </p>
                    {ACTIVE.has(job.status) && <div className="progress" />}
                    {job.error && <p className="error small">{job.error}</p>}
                    {job.deferred.length > 0 && <p className="muted small">Ignored by this backend: {job.deferred.join(", ")}</p>}
                    {job.outputs.map((output) => (
                      <div key={output.file}>
                        <SoundClip
                          api={api}
                          path={output.url ?? `/v1/jobs/${job.id}/files/${output.file}`}
                          filename={`${voice.voice_id}-${job.id}.wav`}
                          label={`take ${String(takes.length - index).padStart(2, "0")}`}
                          seed={voice.seed}
                        />
                        <ChecksBadges checks={output.checks} />
                      </div>
                    ))}
                  </article>
                ))}
              </section>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
