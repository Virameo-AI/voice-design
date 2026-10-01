import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import type { Job, VoiceClient } from "./client.ts";

const VOICE_FILES = new Set(["master.wav", "preview.txt", "instruct.txt", "voice.json"]);

export function safeName(name: string): string {
  if (!name || name !== name.trim() || name.includes("/") || name.includes("\\") || name.includes("..")) {
    throw new Error(`bad file name ${name}`);
  }
  return name;
}

export function voiceFileName(name: string): string {
  const file = safeName(name);
  if (!VOICE_FILES.has(file)) throw new Error(`voice files are ${[...VOICE_FILES].join(", ")}`);
  return file;
}

export async function saveDownload(client: VoiceClient, urlPath: string, dest: string): Promise<string> {
  mkdirSync(dirname(dest), { recursive: true });
  await client.download(urlPath, dest);
  return dest;
}

export interface SavedTake {
  file: string;
  path: string;
  seed: number | null;
  duration_s: number;
  ok: boolean;
  warnings: string[];
}

export async function saveDesignTakes(client: VoiceClient, outDir: string, job: Job): Promise<SavedTake[]> {
  const saved: SavedTake[] = [];
  for (const output of job.outputs) {
    const file = safeName(output.file);
    const dest = join(outDir, "designs", safeName(job.id), file);
    await saveDownload(client, `/v1/jobs/${encodeURIComponent(job.id)}/files/${encodeURIComponent(file)}`, dest);
    saved.push({
      file,
      path: dest,
      seed: output.seed,
      duration_s: output.checks.duration_s,
      ok: output.checks.ok,
      warnings: output.checks.warnings,
    });
  }
  return saved;
}

export function speechPath(outDir: string, voiceId: string, speechId: string): string {
  return join(outDir, `${safeName(voiceId)}-${safeName(speechId)}.wav`);
}

export function voicePath(outDir: string, voiceId: string, file: string): string {
  return join(outDir, "voices", safeName(voiceId), voiceFileName(file));
}

export function templatePath(outDir: string, templateId: string): string {
  return join(outDir, "templates", `${safeName(templateId)}.wav`);
}
