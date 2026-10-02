import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { nextStep, type Job, type VoiceClient } from "./client.ts";
import { saveDesignTakes, saveDownload, speechPath, templatePath, voiceFileName, voicePath } from "./files.ts";
import { LIBRARY_TOOL_NAMES, registerLibraryTools } from "./tools_library.ts";

export const TOOL_NAMES = [
  ...LIBRARY_TOOL_NAMES,
  "design_voice",
  "list_designs",
  "get_design",
  "preview_voice",
  "lock_voice",
  "list_voices",
  "get_voice",
  "delete_voice",
  "download_voice",
  "speak",
  "render_narration",
  "list_speech",
  "get_speech",
  "download_speech",
  "list_templates",
  "get_template",
  "save_template",
  "update_template",
  "duplicate_template",
  "delete_template",
  "preview_template",
  "set_template_sample",
  "list_profile",
  "save_profile_voice",
  "remove_profile_voice",
  "list_jobs",
  "get_job",
  "cancel_job",
  "delete_job",
] as const;

const voiceId = z.string().regex(/^[a-z0-9][a-z0-9-]{1,62}$/).describe("Lowercase letters, digits, and dashes. Example: narrator-v1.");

const params = z
  .object({
    temperature: z.number().gt(0).lte(2).optional(),
    top_p: z.number().gt(0).lte(1).optional(),
    top_k: z.number().int().min(1).max(1000).optional(),
    repetition_penalty: z.number().min(1).max(2).optional(),
    max_tokens: z.number().int().min(64).max(8192).optional(),
    speed: z.number().min(0.5).max(2).optional(),
  })
  .optional()
  .describe("Only the keys you want to change. Empty uses the server defaults.");

function text(data: unknown) {
  return { content: [{ type: "text" as const, text: JSON.stringify(data, null, 2) }] };
}

function failure(err: unknown) {
  const message = err instanceof Error ? err.message : String(err);
  return { isError: true as const, content: [{ type: "text" as const, text: message }] };
}

function compact(body: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(Object.entries(body).filter(([, value]) => value !== undefined));
}

function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

function summary(job: Job) {
  return {
    id: job.id,
    type: job.type,
    status: job.status,
    voice_id: job.voice_id,
    version_id: job.version_id ?? null,
    error: job.error,
    progress: job.progress ?? null,
    next: nextStep(job),
    outputs: job.outputs.map((output) => ({
      file: output.file,
      url: output.url,
      seed: output.seed,
      duration_s: output.checks.duration_s,
      ok: output.checks.ok,
      warnings: output.checks.warnings,
    })),
  };
}

type ToolConfig = {
  title: string;
  description: string;
  inputSchema?: Record<string, z.ZodTypeAny>;
};

export function registerTools(server: McpServer, client: VoiceClient, outDir: string): void {
  const register = server.registerTool.bind(server) as (
    name: string,
    config: ToolConfig,
    handler: (args: any) => Promise<{ content: { type: "text"; text: string }[]; isError?: boolean }>,
  ) => void;
  const add = (name: (typeof TOOL_NAMES)[number], config: ToolConfig, run: (args: any) => Promise<unknown>) => {
    register(name, config, async (args) => {
      try {
        return text(await run(args ?? {}));
      } catch (err) {
        return failure(err);
      }
    });
  };
  registerLibraryTools(add, client, outDir);

  add(
    "design_voice",
    {
      title: "Design candidate voices",
      description:
        "Create several candidate speakers from a description and wait until they are ready. On a 24 GB Mac, four takes take a few minutes. This call waits up to 20 minutes. If it times out, the error names the job. Call get_job with that id. progress.completed counts finished takes. Do not submit a second design for the same request while the first is queued or running. Then lock_voice with the design id and candidate number. Each candidate WAV is saved on disk and the result is its path, not the audio bytes.",
      inputSchema: {
        instruct: z.string().describe("Who is speaking: gender, age, pitch, pace, accent, role."),
        text: z.string().describe("The preview line every candidate reads."),
        language: z.string().optional().describe("Default English."),
        candidates: z.number().int().min(1).max(8).optional().describe("How many candidates. Default 4."),
        seed_start: z.number().int().min(0).optional(),
        params,
      },
    },
    async (args) => {
      const created = await client.post<Job>("/v1/designs", compact({
        instruct: args.instruct,
        text: args.text,
        language: args.language ?? "English",
        candidates: args.candidates ?? 4,
        seed_start: args.seed_start ?? 1000,
        params: args.params ? compact(args.params) : undefined,
      }));
      const done = await client.wait(`/v1/designs/${created.id}`, 20 * 60 * 1000);
      return { id: done.id, status: done.status, candidates: await saveDesignTakes(client, outDir, done) };
    },
  );

  add("list_designs", {
    title: "List voice designs",
    description: "Recent design jobs, newest first.",
    inputSchema: { limit: z.number().int().min(1).max(500).optional() },
  }, async (args) => client.get(`/v1/designs${query({ limit: args.limit })}`));

  add("get_design", {
    title: "Read a voice design",
    description: "One design job, including each candidate's checks and download url.",
    inputSchema: { design_id: z.string() },
  }, async (args) => summary(await client.get<Job>(`/v1/designs/${encodeURIComponent(args.design_id)}`)));

  add(
    "preview_voice",
    {
      title: "Download design previews",
      description:
        "Save candidate WAVs from an existing design onto disk and return their absolute paths. Omit candidate to save every take. Use this before lock_voice when the agent needs to hear or analyze a preview.",
      inputSchema: {
        design_id: z.string(),
        candidate: z.number().int().min(1).optional().describe("1 is candidate-01.wav. Omit to save every candidate."),
      },
    },
    async (args) => {
      const job = await client.get<Job>(`/v1/designs/${encodeURIComponent(args.design_id)}`);
      if (job.status !== "succeeded") throw new Error(`design is ${job.status}`);
      const wanted = args.candidate ? job.outputs.filter((output) => output.file === `candidate-${String(args.candidate).padStart(2, "0")}.wav`) : job.outputs;
      if (wanted.length === 0) throw new Error("candidate not found");
      return { id: job.id, candidates: await saveDesignTakes(client, outDir, { ...job, outputs: wanted }) };
    },
  );

  add(
    "lock_voice",
    {
      title: "Lock a candidate",
      description: "Save one design candidate as a permanent voice_id. Use a new id such as narrator-v2 for a new version.",
      inputSchema: {
        voice_id: voiceId,
        from_design: z.string().describe("Design id returned by design_voice."),
        candidate: z.number().int().min(1).describe("1 is candidate-01.wav."),
        name: z.string().optional(),
        notes: z.string().optional(),
      },
    },
    async (args) => {
      const created = await client.post<Job>("/v1/voices", compact(args));
      const done = await client.wait(`/v1/jobs/${created.id}`, 10 * 60 * 1000);
      return { voice_id: args.voice_id, status: done.status };
    },
  );

  add("list_voices", { title: "List locked voices", description: "Voices that can be used for speech. Each voice_id is permanent." }, async () => client.get("/v1/voices"));

  add("get_voice", {
    title: "Read one locked voice",
    description: "The saved description, preview line, and which design candidate it came from.",
    inputSchema: { voice_id: voiceId },
  }, async (args) => client.get(`/v1/voices/${encodeURIComponent(args.voice_id)}`));

  add("delete_voice", {
    title: "Delete a locked voice",
    description: "Remove a voice_id. Speech already generated with it stays on disk.",
    inputSchema: { voice_id: voiceId },
  }, async (args) => {
    await client.del(`/v1/voices/${encodeURIComponent(args.voice_id)}`);
    return { deleted: args.voice_id };
  });

  add(
    "download_voice",
    {
      title: "Download a locked voice file",
      description: "Save master.wav, preview.txt, instruct.txt, or voice.json and return the absolute path.",
      inputSchema: {
        voice_id: voiceId,
        file: z.enum(["master.wav", "preview.txt", "instruct.txt", "voice.json"]).optional().describe("Default master.wav."),
      },
    },
    async (args) => {
      const file = voiceFileName(args.file ?? "master.wav");
      const dest = voicePath(outDir, args.voice_id, file);
      await saveDownload(client, `/v1/voices/${encodeURIComponent(args.voice_id)}/files/${encodeURIComponent(file)}`, dest);
      return { voice_id: args.voice_id, file: dest };
    },
  );

  add(
    "speak",
    {
      title: "Speak with a locked voice",
      description: "Speak a short script with a locked voice and wait up to 10 minutes. Returns a file path, not audio bytes. A script of several minutes should use render_narration instead. That tool returns immediately and you poll get_job. If this call times out, call get_job. Do not send the same text again while this job is queued or running.",
      inputSchema: {
        voice_id: voiceId,
        version_id: z.string().optional().describe("A voice version such as narrator-v1@2. Default: the current version."),
        text: z.string().describe("One paragraph per line. Lines are generated separately and joined."),
        language: z.string().optional(),
        seed: z.number().int().min(0).optional().describe("Same seed and text produce the same take."),
        params,
      },
    },
    async (args) => {
      const created = await client.post<Job>("/v1/speech", compact({
        voice_id: args.voice_id,
        version_id: args.version_id,
        text: args.text,
        language: args.language ?? "English",
        seed: args.seed ?? 1,
        params: args.params ? compact(args.params) : undefined,
      }));
      const done = await client.wait(`/v1/speech/${created.id}`, 10 * 60 * 1000);
      const file = speechPath(outDir, args.voice_id, done.id);
      await saveDownload(client, `/v1/speech/${done.id}/audio`, file);
      const output = done.outputs[0];
      return {
        file,
        voice_id: args.voice_id,
        speech_id: done.id,
        duration_s: output?.checks.duration_s ?? null,
        ok: output?.checks.ok ?? null,
        warnings: output?.checks.warnings ?? [],
      };
    },
  );

  add("list_speech", {
    title: "List speech jobs",
    description: "Recent spoken takes, newest first.",
    inputSchema: { limit: z.number().int().min(1).max(500).optional() },
  }, async (args) => client.get(`/v1/speech${query({ limit: args.limit })}`));

  add("get_speech", {
    title: "Read a speech job",
    description: "Status, checks, and the download url for one spoken take.",
    inputSchema: { speech_id: z.string() },
  }, async (args) => summary(await client.get<Job>(`/v1/speech/${encodeURIComponent(args.speech_id)}`)));

  add(
    "render_narration",
    {
      title: "Start a long narration",
      description:
        "Start a narration and return immediately with the job id. Poll get_job until status is succeeded or failed. progress.completed and progress.total count beats. A 10 minute script is about 30 minutes on a 24 GB Mac and about 30 MB as a WAV. Segment files show up in outputs as they finish. Call download_speech only after succeeded. cancel_job works only while the job is still queued.",
      inputSchema: {
        voice_id: voiceId,
        version_id: z.string().optional().describe("A voice version such as narrator-v1@2. Default: the current version."),
        text: z.string().describe("Up to about ten minutes. [pause 0.8s] sets the gap after a beat."),
        style: z.string().optional().describe("A style id from list_styles. Default narration."),
        language: z.string().optional(),
        seed: z.number().int().min(0).optional(),
        params,
      },
    },
    async (args) => {
      const created = await client.post<Job>("/v1/renders", compact({
        voice_id: args.voice_id,
        version_id: args.version_id,
        text: args.text,
        style: args.style ?? "narration",
        language: args.language ?? "English",
        seed: args.seed ?? 1,
        params: args.params ? compact(args.params) : undefined,
      }));
      return summary(created);
    },
  );

  add("download_speech", {
    title: "Download a finished speech",
    description: "Write a succeeded speech or narration WAV to disk and return the absolute path. Refuses a job that is still queued or running. The tool result never contains the audio bytes. A 10 minute file is about 30 MB.",
    inputSchema: { speech_id: z.string() },
  }, async (args) => {
    const job = await client.get<Job>(`/v1/jobs/${encodeURIComponent(args.speech_id)}`);
    if (job.status !== "succeeded" || !job.voice_id) throw new Error(`${job.status}. ${nextStep(job)}`);
    const file = speechPath(outDir, job.voice_id, job.id);
    await saveDownload(client, `/v1/jobs/${encodeURIComponent(job.id)}/files/audio.wav`, file);
    return { file, voice_id: job.voice_id, speech_id: job.id };
  });

  add("list_templates", { title: "List voice templates", description: "Built-in and saved voice recipes: description, preview line, and whether a sample clip exists." }, async () => client.get("/v1/templates"));

  add("get_template", {
    title: "Read one voice template",
    description: "The full recipe. Use its instruct and text with design_voice.",
    inputSchema: { template_id: z.string() },
  }, async (args) => client.get(`/v1/templates/${encodeURIComponent(args.template_id)}`));

  add(
    "save_template",
    {
      title: "Save a voice template",
      description: "Store a voice recipe for later designs. Attach a design candidate when you want the template to keep that sample clip.",
      inputSchema: {
        name: z.string(),
        role: z.string(),
        notes: z.string().optional(),
        instruct: z.string(),
        text: z.string(),
        language: z.string().optional(),
        candidates: z.number().int().min(1).max(8).optional(),
        seed_start: z.number().int().min(0).optional(),
        params,
        from_job: z.string().optional().describe("Design id. Send with candidate."),
        candidate: z.number().int().min(1).optional(),
      },
    },
    async (args) => {
      if ((args.from_job == null) !== (args.candidate == null)) throw new Error("from_job and candidate are sent together");
      return client.post("/v1/templates", compact({
        name: args.name,
        role: args.role,
        notes: args.notes,
        instruct: args.instruct,
        text: args.text,
        language: args.language ?? "English",
        candidates: args.candidates ?? 4,
        seed_start: args.seed_start ?? 1000,
        params: args.params ? compact(args.params) : {},
        from_job: args.from_job,
        candidate: args.candidate,
      }));
    },
  );

  add("update_template", {
    title: "Edit a user template",
    description: "Change a saved template. Built-in templates stay as shipped.",
    inputSchema: {
      template_id: z.string(),
      name: z.string().optional(),
      role: z.string().optional(),
      notes: z.string().optional(),
      instruct: z.string().optional(),
      text: z.string().optional(),
      language: z.string().optional(),
      candidates: z.number().int().min(1).max(8).optional(),
      seed_start: z.number().int().min(0).optional(),
      params,
    },
  }, async (args) => {
    const { template_id, params: generation, ...rest } = args;
    return client.patch(`/v1/templates/${encodeURIComponent(template_id)}`, compact({ ...rest, params: generation ? compact(generation) : undefined }));
  });

  add("duplicate_template", {
    title: "Copy a voice template",
    description: "Copy a built-in or saved template into a new user template.",
    inputSchema: { template_id: z.string(), name: z.string().optional() },
  }, async (args) => client.post(`/v1/templates/${encodeURIComponent(args.template_id)}/duplicate`, compact({ name: args.name })));

  add("delete_template", {
    title: "Delete a user template",
    description: "Remove a saved template. Built-in templates stay as shipped.",
    inputSchema: { template_id: z.string() },
  }, async (args) => {
    await client.del(`/v1/templates/${encodeURIComponent(args.template_id)}`);
    return { deleted: args.template_id };
  });

  add("preview_template", {
    title: "Download a template sample",
    description: "Save the template's sample clip and return the absolute path.",
    inputSchema: { template_id: z.string() },
  }, async (args) => {
    const dest = templatePath(outDir, args.template_id);
    await saveDownload(client, `/v1/templates/${encodeURIComponent(args.template_id)}/sample`, dest);
    return { file: dest };
  });

  add("set_template_sample", {
    title: "Replace a template sample",
    description: "Point a user template's sample clip at one design candidate.",
    inputSchema: {
      template_id: z.string(),
      from_job: z.string(),
      candidate: z.number().int().min(1),
    },
  }, async (args) => client.put(`/v1/templates/${encodeURIComponent(args.template_id)}/sample`, { from_job: args.from_job, candidate: args.candidate }));

  add("list_profile", { title: "List profile voices", description: "Locked voices kept on the profile for reuse." }, async () => client.get("/v1/favorites"));

  add("save_profile_voice", {
    title: "Keep a voice on the profile",
    description: "Add or update a locked voice on the profile.",
    inputSchema: { voice_id: voiceId, note: z.string().optional() },
  }, async (args) => client.put(`/v1/favorites/${encodeURIComponent(args.voice_id)}`, compact({ note: args.note })));

  add("remove_profile_voice", {
    title: "Remove a voice from the profile",
    description: "Take a voice off the profile. The locked voice itself remains.",
    inputSchema: { voice_id: voiceId },
  }, async (args) => {
    await client.del(`/v1/favorites/${encodeURIComponent(args.voice_id)}`);
    return { removed: args.voice_id };
  });

  add("list_jobs", {
    title: "List jobs",
    description: "Design, lock, speech, and narration jobs, newest first. Use status=running to see what is still working.",
    inputSchema: {
      status: z.enum(["queued", "running", "succeeded", "failed", "cancelled"]).optional(),
      type: z.enum(["design", "lock", "speak", "render"]).optional(),
      limit: z.number().int().min(1).max(500).optional(),
    },
  }, async (args) => client.get(`/v1/jobs${query(args)}`));

  add("get_job", {
    title: "Read a job",
    description: "Status, progress, and the next action for any job. Call this every 15 seconds while a job is queued or running. progress.detail says what the worker is doing. next says whether to wait, download, or submit again.",
    inputSchema: { job_id: z.string() },
  }, async (args) => summary(await client.get<Job>(`/v1/jobs/${encodeURIComponent(args.job_id)}`)));

  add("cancel_job", {
    title: "Cancel a queued job",
    description: "Cancel a job that is still queued. A running job returns an error. Wait for it, or let it finish, then delete_job if you do not want the audio.",
    inputSchema: { job_id: z.string() },
  }, async (args) => summary(await client.request<Job>("DELETE", `/v1/jobs/${encodeURIComponent(args.job_id)}`)));

  add("delete_job", {
    title: "Delete a job and its audio",
    description: "Remove a finished or failed job and the audio stored for it.",
    inputSchema: { job_id: z.string() },
  }, async (args) => {
    await client.del(`/v1/jobs/${encodeURIComponent(args.job_id)}/record`);
    return { deleted: args.job_id };
  });
}
