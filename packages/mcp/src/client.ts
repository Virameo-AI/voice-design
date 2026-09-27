// HTTP client for the voice-generator studio. The MCP process never loads a model.

export interface Job {
  id: string;
  type: string;
  status: string;
  spec: Record<string, unknown>;
  error: string | null;
  voice_id: string | null;
  outputs: Array<{
    file: string;
    url: string | null;
    seed: number | null;
    sample_rate: number;
    checks: { duration_s: number; ok: boolean; warnings: string[] };
  }>;
}

const TERMINAL = new Set(["succeeded", "failed", "cancelled"]);

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

  async post<T>(path: string, body: unknown): Promise<T> {
    const response = await this.send(path, { method: "POST", headers: this.headers(true), body: JSON.stringify(body) });
    return (await response.json()) as T;
  }

  async get<T>(path: string): Promise<T> {
    const response = await this.send(path, { headers: this.headers() });
    return (await response.json()) as T;
  }

  async wait(path: string, timeoutMs: number): Promise<Job> {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      const job = await this.get<Job>(path);
      if (TERMINAL.has(job.status)) {
        if (job.status !== "succeeded") throw new Error(job.error ?? `job ${job.status}`);
        return job;
      }
      await Bun.sleep(1500);
    }
    throw new Error(`timed out waiting for ${path}`);
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
