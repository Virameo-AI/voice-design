// Playgrounds, voice versions, styles, narrations, downloads.
// Same API the dashboard uses, so an agent and a person see the same objects.
import { z } from "zod";
import { nextStep, type Job, type VoiceClient } from "./client.ts";
import { saveDownload, safeName } from "./files.ts";
import { join } from "node:path";

export const LIBRARY_TOOL_NAMES = [
  "list_playgrounds",
  "create_playground",
  "get_playground",
  "update_playground",
  "copy_playground",
  "run_playground",
  "delete_playground",
  "update_voice",
  "copy_voice",
  "list_voice_versions",
  "download_voice_version",
  "list_styles",
  "save_style",
  "update_style",
  "delete_style",
  "list_narrations",
  "create_narration",
  "get_narration",
  "update_narration",
  "render_saved_narration",
  "copy_narration",
  "delete_narration",
  "download_narration",
  "list_downloads",
] as const;

const voiceId = z.string().regex(/^[a-z0-9][a-z0-9-]{1,62}$/).describe("Lowercase letters, digits, and dashes. Example: narrator-v1.");
const styleId = z.string().regex(/^[a-z0-9][a-z0-9-]{0,62}$/);

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
  .describe("Qwen sampling. Only the keys you want to change.");

const styleFields = {
  name: z.string().max(80).optional(),
  temperature: z.number().gt(0).lte(2).optional(),
  pause_comma_s: z.number().min(0).max(3).optional(),
  pause_period_s: z.number().min(0).max(3).optional(),
  pause_paragraph_s: z.number().min(0).max(5).optional(),
  loudness_dbfs: z.number().min(-40).max(0).optional(),
  crossfade_s: z.number().min(0).max(0.5).optional(),
  emotion: z.string().nullable().optional().describe("A label on the style, or null for none."),
};

function compact(body: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(Object.entries(body).filter(([, value]) => value !== undefined));
}

function query(params: Record<string, string | number | boolean | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

function jobSummary(job: Job) {
  return {
    id: job.id,
    type: job.type,
    status: job.status,
    voice_id: job.voice_id,
    version_id: job.version_id ?? null,
    error: job.error,
    progress: job.progress ?? null,
    next: nextStep(job),
  };
}

const enc = encodeURIComponent;

type Add = (
  name: (typeof LIBRARY_TOOL_NAMES)[number],
  config: { title: string; description: string; inputSchema?: Record<string, z.ZodTypeAny> },
  run: (args: any) => Promise<unknown>,
) => void;

export function registerLibraryTools(add: Add, client: VoiceClient, outDir: string): void {
  // ----- playgrounds -------------------------------------------------------
  add("list_playgrounds", {
    title: "List playgrounds",
    description: "Saved design workspaces, newest first, with how many runs each has.",
    inputSchema: { limit: z.number().int().min(1).max(500).optional() },
  }, async (args) => client.get(`/v1/playgrounds${query({ limit: args.limit })}`));

  add("create_playground", {
    title: "Create a playground",
    description: "Save a design workspace: the description, preview line, language, take count, seed, and Qwen params. Nothing runs yet. Call run_playground to design takes from it. Unknown config keys are kept as sent.",
    inputSchema: {
      name: z.string().min(1).max(80),
      notes: z.string().max(1000).optional(),
      template_id: z.string().optional().describe("Optional template this started from."),
      instruct: z.string().optional().describe("Who is speaking."),
      text: z.string().optional().describe("The preview line."),
      language: z.string().optional(),
      candidates: z.number().int().min(1).max(8).optional(),
      seed_start: z.number().int().min(0).optional(),
      params,
    },
  }, async (args) => {
    const { name, notes, template_id, ...config } = args;
    return client.post("/v1/playgrounds", compact({ name, notes, template_id, config: compact({ ...config, params: config.params ? compact(config.params) : undefined }) }));
  });

  add("get_playground", {
    title: "Read a playground",
    description: "The draft config, every run with its job (status, takes, download urls), and the voices kept from it.",
    inputSchema: { playground_id: z.string() },
  }, async (args) => client.get(`/v1/playgrounds/${enc(args.playground_id)}`));

  add("update_playground", {
    title: "Edit a playground draft",
    description: "Change the name, notes, or config. Runs already made keep their own frozen config.",
    inputSchema: {
      playground_id: z.string(),
      name: z.string().min(1).max(80).optional(),
      notes: z.string().max(1000).optional(),
      config: z.record(z.unknown()).optional().describe("Replaces the whole config object."),
    },
  }, async (args) => {
    const { playground_id, ...rest } = args;
    return client.patch(`/v1/playgrounds/${enc(playground_id)}`, compact(rest));
  });

  add("copy_playground", {
    title: "Copy a playground",
    description: "New playground with the same draft config and no runs.",
    inputSchema: { playground_id: z.string(), name: z.string().max(80).optional() },
  }, async (args) => client.post(`/v1/playgrounds/${enc(args.playground_id)}/copy`, compact({ name: args.name })));

  add("run_playground", {
    title: "Run a playground",
    description: "Queue a design job from the playground config and return immediately. Overrides apply to this run; save=false keeps them out of the draft. Poll get_job; then lock_voice with the job id and a candidate number. The voice is linked back to this playground.",
    inputSchema: {
      playground_id: z.string(),
      instruct: z.string().optional(),
      text: z.string().optional(),
      language: z.string().optional(),
      candidates: z.number().int().min(1).max(8).optional(),
      seed_start: z.number().int().min(0).optional(),
      params,
      save: z.boolean().optional().describe("Default true: write overrides back to the draft."),
    },
  }, async (args) => {
    const { playground_id, ...rest } = args;
    const body = compact({ ...rest, params: rest.params ? compact(rest.params) : undefined });
    return jobSummary(await client.post<Job>(`/v1/playgrounds/${enc(playground_id)}/runs`, body));
  });

  add("delete_playground", {
    title: "Delete a playground",
    description: "Remove the playground and its run records. Voices kept from it stay.",
    inputSchema: { playground_id: z.string() },
  }, async (args) => {
    await client.del(`/v1/playgrounds/${enc(args.playground_id)}`);
    return { deleted: args.playground_id };
  });

  // ----- voices ------------------------------------------------------------
  add("update_voice", {
    title: "Edit a voice",
    description: "Rename, add notes, mark favorite, archive (hides it from lists; narrations keep working), or choose which version is current. The current version is what speak and narrations use when no version_id is given.",
    inputSchema: {
      voice_id: voiceId,
      name: z.string().min(1).max(80).optional(),
      notes: z.string().max(1000).optional(),
      favorite: z.boolean().optional(),
      archived: z.boolean().optional(),
      current_version_id: z.string().optional().describe("Example: narrator-v1@2."),
    },
  }, async (args) => {
    const { voice_id, ...rest } = args;
    return client.patch(`/v1/voices/${enc(voice_id)}`, compact(rest));
  });

  add("copy_voice", {
    title: "Copy a voice",
    description: "Create a new voice_id whose version 1 is one version of an existing voice.",
    inputSchema: {
      voice_id: voiceId.describe("The source voice."),
      new_voice_id: voiceId.describe("The id for the copy."),
      name: z.string().max(80).optional(),
      version_id: z.string().optional().describe("Default: the source's current version."),
    },
  }, async (args) => client.post(`/v1/voices/${enc(args.voice_id)}/copy`, compact({ voice_id: args.new_voice_id, name: args.name, version_id: args.version_id })));

  add("list_voice_versions", {
    title: "List versions of a voice",
    description: "Version 1 is the kept take.",
    inputSchema: { voice_id: voiceId },
  }, async (args) => client.get(`/v1/voices/${enc(args.voice_id)}/versions`));

  add("download_voice_version", {
    title: "Download a version master",
    description: "Write one version's master WAV to disk and return the absolute path.",
    inputSchema: { voice_id: voiceId, version_id: z.string() },
  }, async (args) => {
    const dest = join(outDir, "voices", safeName(args.voice_id), `${safeName(args.version_id).replace("@", "-v")}.wav`);
    await saveDownload(client, `/v1/voices/${enc(args.voice_id)}/versions/${enc(args.version_id)}/master.wav`, dest);
    return { file: dest, voice_id: args.voice_id, version_id: args.version_id };
  });

  // ----- styles ------------------------------------------------------------
  add("list_styles", {
    title: "List styles",
    description: "Delivery presets for narrations: temperature, pauses, loudness, and crossfade. Built-ins are narration, comedy, commercial, kids.",
  }, async () => client.get("/v1/styles"));

  add("save_style", {
    title: "Create a style",
    description: "Make a user style, usually by copying a built-in and changing a few fields. Built-ins themselves stay as shipped.",
    inputSchema: { id: styleId, copy_of: styleId.optional().describe("Start from this style."), ...styleFields },
  }, async (args) => client.post("/v1/styles", compact(args)));

  add("update_style", {
    title: "Edit a user style",
    description: "Change fields on a user style. Narrations already rendered keep the values they used.",
    inputSchema: { style_id: styleId, ...styleFields },
  }, async (args) => {
    const { style_id, ...rest } = args;
    return client.patch(`/v1/styles/${enc(style_id)}`, compact(rest));
  });

  add("delete_style", {
    title: "Delete a user style",
    description: "Removes a user style that no narration uses.",
    inputSchema: { style_id: styleId },
  }, async (args) => {
    await client.del(`/v1/styles/${enc(args.style_id)}`);
    return { deleted: args.style_id };
  });

  // ----- narrations --------------------------------------------------------
  add("list_narrations", {
    title: "List narrations",
    description: "Drafts and rendered narrations, newest first. Filter by voice_id or status (draft, rendering, rendered, failed).",
    inputSchema: { voice_id: voiceId.optional(), status: z.enum(["draft", "rendering", "rendered", "failed"]).optional(), limit: z.number().int().min(1).max(500).optional() },
  }, async (args) => client.get(`/v1/narrations${query(args)}`));

  add("create_narration", {
    title: "Create a narration draft",
    description: "Save a script with one voice version and one style. Nothing renders yet. Edit it with update_narration, then render_saved_narration. The version is frozen into the draft.",
    inputSchema: {
      title: z.string().min(1).max(120),
      notes: z.string().max(1000).optional(),
      voice_id: voiceId,
      version_id: z.string().optional().describe("Default: the voice's current version."),
      style_id: styleId.optional().describe("Default narration."),
      script: z.string().min(1).max(20000).describe("Up to about ten minutes. [laughs], [whispers], [pause 1s] and similar tags mark a beat."),
      language: z.string().optional(),
      params,
      seed: z.number().int().min(0).optional(),
    },
  }, async (args) => client.post("/v1/narrations", compact({ ...args, params: args.params ? compact(args.params) : undefined })));

  add("get_narration", {
    title: "Read a narration",
    description: "The draft or rendered narration, its render job with progress, and audio_url once rendered.",
    inputSchema: { narration_id: z.string() },
  }, async (args) => client.get(`/v1/narrations/${enc(args.narration_id)}`));

  add("update_narration", {
    title: "Edit a narration draft",
    description: "Change any field while the narration is a draft. After rendering only title and notes change; copy_narration starts a new draft.",
    inputSchema: {
      narration_id: z.string(),
      title: z.string().min(1).max(120).optional(),
      notes: z.string().max(1000).optional(),
      voice_id: voiceId.optional(),
      version_id: z.string().optional(),
      style_id: styleId.optional(),
      script: z.string().min(1).max(20000).optional(),
      language: z.string().optional(),
      params,
      seed: z.number().int().min(0).optional(),
    },
  }, async (args) => {
    const { narration_id, ...rest } = args;
    return client.patch(`/v1/narrations/${enc(narration_id)}`, compact({ ...rest, params: rest.params ? compact(rest.params) : undefined }));
  });

  add("render_saved_narration", {
    title: "Render a narration draft",
    description: "Queue the render and return immediately. The draft freezes. Poll get_job (or get_narration) until succeeded; a 10 minute script is about 30 minutes on a 24 GB Mac. Then download_narration. Calling this again while it renders returns an error naming the running job; do not resubmit.",
    inputSchema: { narration_id: z.string() },
  }, async (args) => jobSummary(await client.post<Job>(`/v1/narrations/${enc(args.narration_id)}/render`, {})));

  add("copy_narration", {
    title: "Copy a narration",
    description: "New draft with the same script, voice version, style, and settings.",
    inputSchema: { narration_id: z.string(), title: z.string().max(120).optional() },
  }, async (args) => client.post(`/v1/narrations/${enc(args.narration_id)}/copy`, compact({ name: args.title })));

  add("delete_narration", {
    title: "Delete a narration",
    description: "Remove the narration and its rendered audio. A narration that is rendering cannot be deleted yet.",
    inputSchema: { narration_id: z.string() },
  }, async (args) => {
    await client.del(`/v1/narrations/${enc(args.narration_id)}`);
    return { deleted: args.narration_id };
  });

  add("download_narration", {
    title: "Download a rendered narration",
    description: "Write the final WAV to disk and return the absolute path. Refuses drafts and narrations still rendering. The audio is not inside the tool result; a 10 minute file is about 30 MB.",
    inputSchema: { narration_id: z.string() },
  }, async (args) => {
    const narration = await client.get<{ id: string; title: string; status: string; voice_id: string; job?: Job | null }>(`/v1/narrations/${enc(args.narration_id)}`);
    if (narration.status !== "rendered") {
      const hint = narration.job ? nextStep(narration.job) : "Call render_saved_narration first.";
      throw new Error(`narration is ${narration.status}. ${hint}`);
    }
    const dest = join(outDir, "narrations", `${safeName(narration.voice_id)}-${safeName(narration.id)}.wav`);
    await saveDownload(client, `/v1/narrations/${enc(narration.id)}/audio.wav`, dest);
    return { file: dest, narration_id: narration.id, title: narration.title, voice_id: narration.voice_id };
  });

  add("list_downloads", {
    title: "List everything downloadable",
    description: "Rendered narrations, voice version masters, and spoken takes, newest first, each with its url. Use download_narration, download_voice_version, or download_speech to write one to disk.",
    inputSchema: { limit: z.number().int().min(1).max(500).optional() },
  }, async (args) => client.get(`/v1/downloads${query({ limit: args.limit })}`));
}
