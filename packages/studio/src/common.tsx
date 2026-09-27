import type { ReactNode } from "react";
import { ApiError, type Checks, type GenParams, type JobStatus } from "./api";

export const LANGUAGES = ["English", "Chinese", "Japanese", "Korean", "German", "French", "Spanish", "Italian", "Portuguese", "Russian"];

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return String(err);
}

export function fmtTime(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString(undefined, { hour12: false });
}

export function fmtDate(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleString(undefined, { hour12: false, month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function secondsBetween(a: string | null, b: string | null): string {
  if (!a || !b) return "";
  return `${((new Date(b).getTime() - new Date(a).getTime()) / 1000).toFixed(1)} s`;
}

export function shorten(s: string, n = 60): string {
  return s.length > n ? `${s.slice(0, n)}…` : s;
}

export function StatusBadge({ status }: { status: JobStatus }) {
  return <span className={`badge status-${status}`}>{status}</span>;
}

const WARNING_LABELS: Record<string, string> = {
  too_short: "very short",
  clipping: "clipping",
  too_quiet: "too quiet",
  long_lead: "silence at start",
  long_tail: "silence at end",
  pace_fast: "pace fast",
  pace_slow: "pace slow",
};

export function ChecksBadges({ checks, warningsOnly = false }: { checks: Checks; warningsOnly?: boolean }) {
  return (
    <div className="metrics">
      {!warningsOnly && (
        <>
          <span className="metric">{checks.duration_s.toFixed(1)} s</span>
          <span className="metric">peak {checks.peak.toFixed(2)}</span>
          <span className="metric">RMS {checks.rms_dbfs.toFixed(0)} dBFS</span>
        </>
      )}
      {checks.ok ? (
        <span className="metric ok">ok</span>
      ) : (
        checks.warnings.map((w) => (
          <span key={w} className="metric warn" title={w}>
            {WARNING_LABELS[w] ?? w}
          </span>
        ))
      )}
    </div>
  );
}

export function Field({ label, hint, children, inline = false }: { label: string; hint?: string; children: ReactNode; inline?: boolean }) {
  return (
    <label className={inline ? "field inline" : "field"}>
      <span className="label">
        {label}
        {hint && <small>{hint}</small>}
      </span>
      {children}
    </label>
  );
}

interface ParamDef {
  key: keyof GenParams;
  label: string;
  placeholder: string;
  step: number;
  min: number;
  max: number;
}

const PARAM_DEFS: ParamDef[] = [
  { key: "temperature", label: "Temperature", placeholder: "0.9", step: 0.05, min: 0.05, max: 2 },
  { key: "top_p", label: "Top-p", placeholder: "1.0", step: 0.05, min: 0.05, max: 1 },
  { key: "top_k", label: "Top-k", placeholder: "50", step: 1, min: 1, max: 1000 },
  { key: "repetition_penalty", label: "Repetition penalty", placeholder: "1.05", step: 0.01, min: 1, max: 2 },
  { key: "max_tokens", label: "Max tokens", placeholder: "4096", step: 64, min: 64, max: 8192 },
  { key: "speed", label: "Speed (Mac)", placeholder: "1.0", step: 0.05, min: 0.5, max: 2 },
];

export function ParamFields({ value, onChange, showSpeed, extra }: { value: GenParams; onChange: (next: GenParams) => void; showSpeed: boolean; extra?: ReactNode }) {
  const defs = PARAM_DEFS.filter((d) => showSpeed || d.key !== "speed");
  const changed = Object.keys(value).length;
  return (
    <details className="params">
      <summary>
        Advanced model settings
        <small>{changed ? `${changed} changed` : "server defaults"}</small>
      </summary>
      <div className="grid two">
        {extra}
        {defs.map((d) => (
          <Field key={d.key} label={d.label}>
            <input
              type="number"
              step={d.step}
              min={d.min}
              max={d.max}
              placeholder={d.placeholder}
              value={value[d.key] ?? ""}
              onChange={(e) => {
                const next = { ...value };
                if (e.target.value === "") delete next[d.key];
                else next[d.key] = Number(e.target.value);
                onChange(next);
              }}
            />
          </Field>
        ))}
      </div>
      {changed > 0 && (
        <button type="button" className="ghost small" onClick={() => onChange({})}>
          Reset to defaults
        </button>
      )}
    </details>
  );
}
