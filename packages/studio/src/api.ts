// Everything the UI knows about the backend goes through this file, over HTTP.
// Requests stay on the same origin: the studio proxies them to the engine.

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

export type JobStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";
export type JobType = "design" | "lock" | "speak";

export interface Job {
  id: string;
  type: JobType;
  status: JobStatus;
  spec: Record<string, unknown>;
  backend: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  applied: string[];
  deferred: string[];
  outputs: Output[];
  voice_id: string | null;
  error: string | null;
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
  design_backend: string | null;
  sample_rate: number;
}

export interface VoiceTemplate {
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
  sample_url: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface Favorite {
  voice_id: string;
  profile_note: string | null;
  profile_created_at: string;
  name: string;
  notes: string | null;
  created_at: string;
  language: string;
  from_job: string;
  candidate: number;
  seed: number | null;
  design_backend: string | null;
  sample_rate: number;
}

export interface Health {
  status: string;
  version: string;
  backend: string;
  device: string;
  models_loaded: string[];
  running_job: string | null;
  queued_jobs: number;
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

export interface DesignSpec {
  type: "design";
  instruct: string;
  text: string;
  language: string;
  candidates: number;
  seed_start: number;
  params: GenParams;
}

export interface LockSpec {
  type: "lock";
  voice_id: string;
  from_job: string;
  candidate: number;
  name?: string;
  notes?: string;
}

export interface SpeakSpec {
  type: "speak";
  voice_id: string;
  text: string;
  language: string;
  seed: number;
  params: GenParams;
}

export type JobSpec = DesignSpec | LockSpec | SpeakSpec;

export const ACTIVE: ReadonlySet<JobStatus> = new Set(["queued", "running"]);

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

function detail(body: unknown): string | null {
  if (!body || typeof body !== "object") return null;
  const d = (body as { detail?: unknown }).detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) {
    return d
      .map((item) => {
        const it = item as { loc?: unknown[]; msg?: string };
        const where = (it.loc ?? []).filter((p) => p !== "body").join(".");
        return where ? `${where}: ${it.msg ?? ""}` : (it.msg ?? "");
      })
      .join("; ");
  }
  return null;
}

export class Api {
  readonly base = "";
  private readonly headers: Record<string, string>;

  constructor(public readonly token: string) {
    this.headers = token ? { Authorization: `Bearer ${token}` } : {};
  }

  private async request<T>(path: string, init: RequestInit = {}, timeoutMs = 15000): Promise<T> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    let response: Response;
    try {
      response = await fetch(this.base + path, {
        ...init,
        headers: { ...this.headers, ...(init.headers as Record<string, string> | undefined) },
        signal: controller.signal,
      });
    } catch (err) {
      const reason = err instanceof Error && err.name === "AbortError" ? "timed out" : "unreachable";
      throw new ApiError(0, `${this.base} is ${reason}`);
    } finally {
      clearTimeout(timer);
    }
    if (!response.ok) {
      let body: unknown = null;
      try {
        body = await response.json();
      } catch {
        /* not JSON */
      }
      throw new ApiError(response.status, detail(body) ?? `${response.status} ${response.statusText}`);
    }
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  }

  health(timeoutMs = 4000): Promise<Health> {
    return this.request<Health>("/health", {}, timeoutMs);
  }

  submit(spec: JobSpec): Promise<Job> {
    return this.request<Job>("/v1/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(spec),
    });
  }

  jobs(limit = 200): Promise<Job[]> {
    return this.request<Job[]>(`/v1/jobs?limit=${limit}`);
  }

  job(id: string): Promise<Job> {
    return this.request<Job>(`/v1/jobs/${encodeURIComponent(id)}`);
  }

  cancel(id: string): Promise<Job> {
    return this.request<Job>(`/v1/jobs/${encodeURIComponent(id)}`, { method: "DELETE" });
  }

  voices(): Promise<Voice[]> {
    return this.request<Voice[]>("/v1/voices");
  }

  templates(): Promise<VoiceTemplate[]> {
    return this.request<VoiceTemplate[]>("/v1/templates");
  }

  createTemplate(body: {
    name: string;
    role: string;
    instruct: string;
    text: string;
    language: string;
    candidates: number;
    seed_start: number;
    params: GenParams;
    from_job?: string;
    candidate?: number;
  }): Promise<VoiceTemplate> {
    return this.request<VoiceTemplate>("/v1/templates", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  }

  updateTemplate(id: string, body: Partial<Pick<VoiceTemplate, "name" | "role" | "notes" | "instruct" | "text" | "language" | "candidates" | "seed_start" | "params">>): Promise<VoiceTemplate> {
    return this.request<VoiceTemplate>(`/v1/templates/${encodeURIComponent(id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  }

  deleteTemplate(id: string): Promise<void> {
    return this.request<void>(`/v1/templates/${encodeURIComponent(id)}`, { method: "DELETE" });
  }

  duplicateTemplate(id: string, name?: string): Promise<VoiceTemplate> {
    return this.request<VoiceTemplate>(`/v1/templates/${encodeURIComponent(id)}/duplicate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(name ? { name } : {}),
    });
  }

  replaceTemplateSample(id: string, fromJob: string, candidate: number): Promise<VoiceTemplate> {
    return this.request<VoiceTemplate>(`/v1/templates/${encodeURIComponent(id)}/sample`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ from_job: fromJob, candidate }),
    });
  }

  favorites(): Promise<Favorite[]> {
    return this.request<Favorite[]>("/v1/favorites");
  }

  saveFavorite(voiceId: string, note?: string): Promise<Favorite> {
    return this.request<Favorite>(`/v1/favorites/${encodeURIComponent(voiceId)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(note ? { note } : {}),
    });
  }

  removeFavorite(voiceId: string): Promise<void> {
    return this.request<void>(`/v1/favorites/${encodeURIComponent(voiceId)}`, { method: "DELETE" });
  }

  voiceFilePath(voiceId: string, name: string): string {
    return `/v1/voices/${encodeURIComponent(voiceId)}/files/${name}`;
  }

  /** Files need the auth header, so they are fetched as blobs and played from object URLs. */
  async blob(path: string): Promise<Blob> {
    const response = await fetch(this.base + path, { headers: this.headers });
    if (!response.ok) throw new ApiError(response.status, `could not fetch ${path}`);
    return response.blob();
  }

  docsUrl(): string {
    return "/docs";
  }
}
