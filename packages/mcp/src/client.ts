// HTTP client for the voice engine. The MCP endpoint never loads a model.

export interface Progress {
  phase: string;
  detail: string;
  completed: number;
  total: number;
}

export interface Job {
  id: string;
  type: string;
  status: string;
  spec: Record<string, unknown>;
  error: string | null;
  voice_id: string | null;
  version_id?: string | null;
  progress?: Progress;
  outputs: Array<{
    file: string;
    url: string | null;
    seed: number | null;
    sample_rate: number;
    checks: { duration_s: number; ok: boolean; warnings: string[] };
  }>;
}

const TERMINAL = new Set(["succeeded", "failed", "cancelled"]);

export function nextStep(job: Job): string {
  const where = job.progress?.total
    ? `${job.progress.completed} of ${job.progress.total}. ${job.progress.detail}`
    : (job.progress?.detail ?? "");
  if (job.status === "queued") return `Queued. ${where} Call get_job again in 15 seconds. cancel_job works only while queued.`;
  if (job.status === "running") return `Running. ${where} Call get_job again. audio.wav is not ready. A file already listed in outputs can be downloaded.`;
  if (job.status === "succeeded") return "Succeeded. download_speech or download_voice writes a WAV on disk and returns its path. The audio is not inside the tool result. A 10 minute WAV is about 30 MB.";
  if (job.status === "failed") return `Failed: ${job.error ?? "unknown"}. If this says interrupted by restart, submit the same request again.`;
  return "Cancelled. Submit a new job to try again.";
}

export class VoiceClient {
  constructor(
    private readonly base: string,
    private readonly token: string,
  ) {}

  private headers(json = false): HeadersInit {
    const headers: Record<string, string> = {};
    if (json) headers["content-type"] = "application/json";
    if (this.token) headers.authorization = `Bearer ${this.token}`;
    return headers;
  }

  private async send(path: string, init?: RequestInit): Promise<Response> {
    let response: Response;
    try {
      response = await fetch(this.base + path, init);
    } catch {
      throw new Error(`${this.base} is unreachable. Start it with \`bun start.ts\`.`);
    }
    if (!response.ok) {
      let detail = `${response.status} ${response.statusText}`;
      try {
        const body = (await response.json()) as { detail?: unknown };
        if (typeof body.detail === "string") detail = body.detail;
      } catch {
        /* not json */
      }
      throw new Error(detail);
    }
    return response;
  }

  async request<T>(method: string, path: string, body?: unknown): Promise<T> {
    const response = await this.send(path, {
      method,
      headers: this.headers(body !== undefined),
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (response.status === 204) return undefined as T;
    const text = await response.text();
    if (!text) return undefined as T;
    return JSON.parse(text) as T;
  }

  async post<T>(path: string, body: unknown): Promise<T> {
    return this.request<T>("POST", path, body);
  }

  async get<T>(path: string): Promise<T> {
    return this.request<T>("GET", path);
  }

  async put<T>(path: string, body: unknown): Promise<T> {
    return this.request<T>("PUT", path, body);
  }

  async patch<T>(path: string, body: unknown): Promise<T> {
    return this.request<T>("PATCH", path, body);
  }

  async del(path: string): Promise<void> {
    await this.request<void>("DELETE", path);
  }

  async wait(path: string, timeoutMs: number): Promise<Job> {
    const deadline = Date.now() + timeoutMs;
    let last: Job | undefined;
    while (Date.now() < deadline) {
      last = await this.get<Job>(path);
      if (TERMINAL.has(last.status)) {
        if (last.status !== "succeeded") throw new Error(`${last.error ?? last.status}. ${nextStep(last)}`);
        return last;
      }
      await Bun.sleep(1500);
    }
    const waited = Math.round(timeoutMs / 1000);
    throw new Error(`still ${last?.status ?? "unknown"} after ${waited}s. ${last ? nextStep(last) : path}`);
  }

  async download(path: string, dest: string): Promise<void> {
    const response = await this.send(path, { headers: this.headers() });
    await Bun.write(dest, await response.arrayBuffer());
  }
}

export function voiceClientFromEnv(): VoiceClient {
  const base = (process.env.VOICE_GENERATOR_URL ?? "http://127.0.0.1:8180").replace(/\/+$/, "");
  return new VoiceClient(base, process.env.VOICE_GENERATOR_TOKEN ?? "");
}
