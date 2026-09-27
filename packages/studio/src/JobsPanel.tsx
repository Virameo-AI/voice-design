import { useEffect, useMemo, useState } from "react";
import type { Api, Job, JobStatus, JobType } from "./api";
import { ChecksBadges, errorMessage, Field, fmtDate, secondsBetween, StatusBadge } from "./common";
import { SoundClip } from "./SoundClip";

const TYPES: JobType[] = ["design", "lock", "speak"];
const STATUSES: JobStatus[] = ["queued", "running", "succeeded", "failed", "cancelled"];

export function JobsView({ api, jobs, onChanged }: { api: Api; jobs: Job[]; onChanged: () => void }) {
  const [types, setTypes] = useState<Set<JobType>>(new Set(TYPES));
  const [status, setStatus] = useState<JobStatus | "">("");
  const [query, setQuery] = useState("");
  const [openId, setOpenId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return jobs.filter((job) => types.has(job.type) && (!status || job.status === status) && (!needle || summary(job).toLowerCase().includes(needle) || job.id.includes(needle)));
  }, [jobs, types, status, query]);

  const open = openId ? (jobs.find((job) => job.id === openId) ?? null) : null;

  useEffect(() => {
    if (openId && !visible.some((job) => job.id === openId)) setOpenId(null);
  }, [visible, openId]);

  async function cancel(id: string) {
    try {
      await api.cancel(id);
      onChanged();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <section className="view" aria-label="Activity">
      <div className="subhero">
        <span className="eyebrow">Your voice studio / 03</span>
        <h1>
          Everything in <em>motion.</em>
        </h1>
        <p className="lead">Voice previews, saved voices, and speech takes.</p>
      </div>
      <div className="jobs-layout">
        <section className="panel pad filters">
          <h2>Filter</h2>
          <Field label="Search">
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Text, voice id, or job id" />
          </Field>
          <fieldset className="type-filters">
            <legend>Type</legend>
            {TYPES.map((type) => (
              <label key={type}>
                <input
                  type="checkbox"
                  checked={types.has(type)}
                  onChange={(event) => {
                    const next = new Set(types);
                    if (event.target.checked) next.add(type);
                    else next.delete(type);
                    setTypes(next);
                  }}
                />
                {type}
              </label>
            ))}
          </fieldset>
          <Field label="Status">
            <select value={status} onChange={(e) => setStatus(e.target.value as JobStatus | "")}>
              <option value="">Any</option>
              {STATUSES.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </Field>
          {error && <p className="error">{error}</p>}
        </section>
        <div className="activity">
          {visible.length === 0 && <p className="muted empty">Nothing matches.</p>}
          {visible.map((job) => (
            <article key={job.id} className={open?.id === job.id ? "panel job selected" : "panel job"}>
              <button
                type="button"
                className="job-open"
                aria-expanded={open?.id === job.id}
                aria-controls={`detail-${job.id}`}
                onClick={() => setOpenId((current) => (current === job.id ? null : job.id))}
              >
                <span className="job-head">
                  <strong>{headline(job)}</strong>
                  <StatusBadge status={job.status} />
                </span>
                <span className="job-summary">{summary(job)}</span>
                <small>
                  {fmtDate(job.created_at)} · {job.type}
                  {job.finished_at ? ` · ${secondsBetween(job.started_at, job.finished_at)}` : ""}
                </small>
              </button>
              {open?.id === job.id && (
                <div className="job-detail" id={`detail-${job.id}`}>
                  <p className="muted small">
                    <code>{job.id}</code>
                    {job.backend ? ` · ${job.backend}` : ""}
                    {job.applied.length > 0 ? ` · applied ${job.applied.join(", ")}` : ""}
                    {job.deferred.length > 0 ? ` · ignored ${job.deferred.join(", ")}` : ""}
                  </p>
                  {job.error && <p className="error">{job.error}</p>}
                  {job.status === "queued" && (
                    <button type="button" className="secondary" onClick={() => void cancel(job.id)}>
                      Cancel job
                    </button>
                  )}
                  {job.outputs.map((output, index) => (
                    <div key={output.file} className="take">
                      <SoundClip
                        api={api}
                        path={output.url ?? `/v1/jobs/${job.id}/files/${output.file}`}
                        filename={`${job.id}-${output.file}`}
                        label={job.type === "design" ? `candidate ${index + 1}` : job.type === "lock" ? "reference clip" : "speech take"}
                        seed={output.seed}
                        load="request"
                      />
                      <ChecksBadges checks={output.checks} />
                    </div>
                  ))}
                  <details className="advanced">
                    <summary>Request</summary>
                    <pre className="spec">{JSON.stringify(job.spec, null, 2)}</pre>
                  </details>
                </div>
              )}
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

function summary(job: Job): string {
  if (job.type === "design") return `${job.outputs.length} of ${String(job.spec.candidates)} candidates. ${String(job.spec.instruct ?? "")}`;
  if (job.type === "lock") return `${String(job.spec.voice_id)} from candidate ${String(job.spec.candidate)}.`;
  return `${String(job.spec.voice_id)}: ${String(job.spec.text ?? "")}`;
}

function headline(job: Job): string {
  if (job.type === "design") return "Voice previews";
  if (job.type === "lock") return "Voice saved";
  return "Speech take";
}
