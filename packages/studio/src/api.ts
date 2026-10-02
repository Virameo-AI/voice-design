// Everything the dashboard knows about the backend goes through this file.
// Requests stay on the same origin: the studio server proxies /v1 to the engine.
import { loadToken } from "./config.ts";

export interface Checks {
  duration_s: number;
  peak: number;
  rms_dbfs: number;
  clipped_ratio: number;
  lead_silence_s: number;
  tail_silence_s: number;
  chars_per_s: number | null;
  ok: boolean;
  warnings: string[];
}

export interface Output {
  file: string;
  url: string | null;
  seed: number | null;
  sample_rate: number;
  checks: Checks;
}

export interface Progress {
  phase: string;
  detail: string;
  completed: number;
  total: number;
}

export type JobStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";

export interface Job {
  id: string;
  type: "design" | "lock" | "speak" | "render";
  status: JobStatus;
  progress: Progress;
  spec: Record<string, unknown>;
  backend: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  applied: string[];
  deferred: string[];
  outputs: Output[];
  voice_id: string | null;
  version_id: string | null;
  error: string | null;
}

export interface GenParams {
  temperature?: number;
  top_p?: number;
  top_k?: number;
  repetition_penalty?: number;
  max_tokens?: number;
  speed?: number;
}

export interface Template {
  id: string;
  name: string;
  role: string;
  origin: "builtin" | "user";
  notes: string | null;
  instruct: string;
  text: string;
  language: string;
  candidates: number;
  seed_start: number;
  params: GenParams;
  has_sample: boolean;
}

export interface Playground {
  id: string;
  name: string;
  notes: string | null;
  template_id: string | null;
  config: Record<string, unknown>;
  copied_from: string | null;
  created_at: string;
  updated_at: string;
  runs: Array<{ id: string; run_no: number; job_id: string; config: Record<string, unknown>; created_at: string; job?: Job | null }>;
  run_count?: number;
}

export interface Version {
  id: string;
  voice_id: string;
  version_no: number;
  parent_version_id: string | null;
  kind: string;
  label: string;
  sample_rate: number;
  duration_s: number | null;
  ref_text: string;
  edits: Record<string, unknown>;
  job_id: string | null;
  created_at: string;
}

export interface Voice {
  voice_id: string;
  name: string;
  notes: string | null;
  created_at: string;
  language: string;
  from_job: string;
  candidate: number;
  seed: number | null;
  sample_rate: number;
  playground_id: string | null;
  current_version_id: string | null;
  favorite: boolean;
  archived: boolean;
  copied_from: string | null;
  version_count?: number;
  versions?: Version[];
}

export interface Style {
  id: string;
  name: string;
  builtin: boolean;
  temperature: number;
  pause_comma_s: number;
  pause_period_s: number;
  pause_paragraph_s: number;
  loudness_dbfs: number;
  crossfade_s: number;
  emotion: string | null;
}

export interface Narration {
  id: string;
  title: string;
  notes: string | null;
  voice_id: string;
  version_id: string;
  style_id: string;
  script: string;
  language: string;
  params: GenParams;
  seed: number;
  status: "draft" | "rendering" | "rendered" | "failed";
  job_id: string | null;
  job?: Job | null;
  audio_url?: string;
  created_at: string;
  updated_at: string;
}

export interface Download {
  kind: "narration" | "voice" | "speech";
  id: string;
  title: string;
  voice_id: string | null;
  version_id: string | null;
  style_id: string | null;
  created_at: string;
  duration_s: number | null;
  url: string;
}

export interface Health {
  status: string;
  version: string;
  backend: string;
  device: string;
  models_loaded: boolean;
  running_job: string | null;
  queued_jobs: number;
  error: string | null;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

function headers(json = false): HeadersInit {
  const out: Record<string, string> = {};
  if (json) out["content-type"] = "application/json";
  const token = loadToken();
  if (token) out.authorization = `Bearer ${token}`;
  return out;
}

const UNREACHABLE = `The studio server at ${location.host} did not answer. Check that bun start.ts is still running, then try again.`;

/** fetch() that retries once after a short pause, so a server restart or hot reload does not surface as an error. */
async function reach(path: string, init: RequestInit): Promise<Response> {
  try {
    return await fetch(path, init);
  } catch {
    await new Promise((resolve) => setTimeout(resolve, 800));
    try {
      return await fetch(path, init);
    } catch {
      throw new ApiError(0, UNREACHABLE);
    }
  }
}

async function send<T>(method: string, path: string, body?: unknown): Promise<T> {
  const response = await reach(path, { method, headers: headers(body !== undefined), body: body === undefined ? undefined : JSON.stringify(body) });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const data = (await response.json()) as { detail?: unknown };
      if (typeof data.detail === "string") detail = data.detail;
      else if (Array.isArray(data.detail)) detail = data.detail.map((d: any) => `${(d.loc ?? []).slice(1).join(".")}: ${d.msg}`).join("; ");
    } catch {
      /* not json */
    }
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

export const api = {
  health: () => send<Health>("GET", "/health"),
  mcpAlive: async (): Promise<boolean> => {
    try {
      const response = await fetch("/mcp", {
        method: "POST",
        headers: { ...headers(true), accept: "application/json, text/event-stream" },
        body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "initialize", params: { protocolVersion: "2025-03-26", capabilities: {}, clientInfo: { name: "studio", version: "0.1" } } }),
      });
      return response.ok;
    } catch {
      return false;
    }
  },

  templates: () => send<Template[]>("GET", "/v1/templates"),

  playgrounds: () => send<Playground[]>("GET", "/v1/playgrounds"),
  playground: (id: string) => send<Playground>("GET", `/v1/playgrounds/${enc(id)}`),
  createPlayground: (body: { name: string; notes?: string; template_id?: string | null; config: Record<string, unknown> }) => send<Playground>("POST", "/v1/playgrounds", body),
  updatePlayground: (id: string, body: Record<string, unknown>) => send<Playground>("PATCH", `/v1/playgrounds/${enc(id)}`, body),
  runPlayground: (id: string, body: Record<string, unknown>) => send<Job>("POST", `/v1/playgrounds/${enc(id)}/runs`, body),

  job: (id: string) => send<Job>("GET", `/v1/jobs/${enc(id)}`),
  jobs: (type?: string, limit = 50) => send<Job[]>("GET", `/v1/jobs?limit=${limit}${type ? `&type=${type}` : ""}`),
  cancelJob: (id: string) => send<Job>("DELETE", `/v1/jobs/${enc(id)}`),

  lockVoice: (body: { voice_id: string; from_design: string; candidate: number; name?: string; notes?: string }) => send<Job>("POST", "/v1/voices", body),
  voices: () => send<Voice[]>("GET", "/v1/voices"),
  voice: (id: string) => send<Voice>("GET", `/v1/voices/${enc(id)}`),
  updateVoice: (id: string, body: Record<string, unknown>) => send<Voice>("PATCH", `/v1/voices/${enc(id)}`, body),
  deleteVoice: (id: string) => send<void>("DELETE", `/v1/voices/${enc(id)}`),
  versions: (id: string) => send<Version[]>("GET", `/v1/voices/${enc(id)}/versions`),

  styles: () => send<Style[]>("GET", "/v1/styles"),

  narrations: () => send<Narration[]>("GET", "/v1/narrations"),
  narration: (id: string) => send<Narration>("GET", `/v1/narrations/${enc(id)}`),
  createNarration: (body: Record<string, unknown>) => send<Narration>("POST", "/v1/narrations", body),
  renderNarration: (id: string) => send<Job>("POST", `/v1/narrations/${enc(id)}/render`, {}),

  downloads: () => send<Download[]>("GET", "/v1/downloads"),

  /** Fetch a protected WAV as an object URL the <audio> element can play. */
  blobUrl: async (path: string): Promise<string> => {
    const response = await reach(path, { headers: headers() });
    if (!response.ok) {
      let detail = `${response.status}`;
      try {
        detail = ((await response.json()) as { detail?: string }).detail ?? detail;
      } catch {
        /* ignore */
      }
      throw new ApiError(response.status, detail);
    }
    try {
      return URL.createObjectURL(await response.blob());
    } catch {
      throw new ApiError(0, "The audio download stopped before it finished. Press play again.");
    }
  },

  /** Poll a job until it leaves the queue. onTick fires on every read. */
  waitJob: async (id: string, onTick?: (job: Job) => void, intervalMs = 1500): Promise<Job> => {
    for (;;) {
      const job = await send<Job>("GET", `/v1/jobs/${enc(id)}`);
      onTick?.(job);
      if (job.status === "succeeded" || job.status === "failed" || job.status === "cancelled") return job;
      await new Promise((resolve) => setTimeout(resolve, intervalMs));
    }
  },
};

function enc(value: string): string {
  return encodeURIComponent(value);
}
