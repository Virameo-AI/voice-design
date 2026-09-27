#!/usr/bin/env bun
// MCP server for Voice Generator. Tools split the same way as the HTTP API:
// voice design, then speech with a locked voice. Speech saves a WAV and
// returns its path so an agent can hand the file to the next step.
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { mkdirSync } from "node:fs";
import { join, resolve } from "node:path";
import { z } from "zod";
import { voiceClientFromEnv, type Job } from "./client.ts";

const client = voiceClientFromEnv();
const outDir = resolve(process.env.VOICE_GENERATOR_OUT ?? "data/out");
const server = new McpServer({ name: "voice-generator", version: "0.1.0" });

function text(data: unknown) {
  return { content: [{ type: "text" as const, text: JSON.stringify(data, null, 2) }] };
}

function failure(err: unknown) {
  const message = err instanceof Error ? err.message : String(err);
  return { isError: true as const, content: [{ type: "text" as const, text: message }] };
}

function summary(job: Job) {
  return {
    id: job.id,
    status: job.status,
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

server.registerTool(
  "list_voices",
  {
    title: "List locked voices",
    description: "Voices that can be used for speech. Each voice_id is permanent.",
  },
  async () => {
    try {
      return text(await client.get("/v1/voices"));
    } catch (err) {
      return failure(err);
    }
  },
);

server.registerTool(
  "design_voice",
  {
    title: "Design candidate voices",
    description:
      "Create several candidate speakers from a description and wait until they are ready. Listen by downloading a candidate url, then lock_voice with the design id and candidate number.",
    inputSchema: {
      instruct: z.string().describe("Who is speaking: gender, age, pitch, pace, accent, role."),
      text: z.string().describe("The preview line every candidate reads."),
      language: z.string().optional().describe("Default English."),
      candidates: z.number().int().min(1).max(8).optional().describe("How many candidates. Default 4."),
      seed_start: z.number().int().min(0).optional(),
    },
  },
  async (args) => {
    try {
      const created = await client.post<Job>("/v1/designs", {
        instruct: args.instruct,
        text: args.text,
        language: args.language ?? "English",
        candidates: args.candidates ?? 4,
        seed_start: args.seed_start ?? 1000,
      });
      const done = await client.wait(`/v1/designs/${created.id}`, 20 * 60 * 1000);
      return text(summary(done));
    } catch (err) {
      return failure(err);
    }
  },
);

server.registerTool(
  "lock_voice",
  {
    title: "Lock a candidate",
    description: "Save one design candidate as a permanent voice_id. Use a new id such as narrator-v2 for a new version.",
    inputSchema: {
      voice_id: z.string().describe("Lowercase letters, digits, and dashes. Example: narrator-v1."),
      from_design: z.string().describe("Design id returned by design_voice."),
      candidate: z.number().int().min(1).describe("1 is candidate-01.wav."),
      name: z.string().optional(),
    },
  },
  async (args) => {
    try {
      const created = await client.post<Job>("/v1/voices", args);
      const done = await client.wait(`/v1/jobs/${created.id}`, 10 * 60 * 1000);
      return text({ voice_id: args.voice_id, status: done.status });
    } catch (err) {
      return failure(err);
    }
  },
);

server.registerTool(
  "speak",
  {
    title: "Speak with a locked voice",
    description:
      "Generate speech from text with a locked voice_id, wait for it, and save the WAV. Returns the absolute file path for the next step.",
    inputSchema: {
      voice_id: z.string(),
      text: z.string().describe("One paragraph per line. Lines are generated separately and joined."),
      language: z.string().optional(),
      seed: z.number().int().min(0).optional().describe("Same seed and text produce the same take."),
    },
  },
  async (args) => {
    try {
      const created = await client.post<Job>("/v1/speech", {
        voice_id: args.voice_id,
        text: args.text,
        language: args.language ?? "English",
        seed: args.seed ?? 1,
      });
      const done = await client.wait(`/v1/speech/${created.id}`, 10 * 60 * 1000);
      mkdirSync(outDir, { recursive: true });
      const file = join(outDir, `${args.voice_id}-${done.id}.wav`);
      await client.download(`/v1/speech/${done.id}/audio`, file);
      const output = done.outputs[0];
      return text({
        file,
        voice_id: args.voice_id,
        speech_id: done.id,
        duration_s: output?.checks.duration_s ?? null,
        ok: output?.checks.ok ?? null,
        warnings: output?.checks.warnings ?? [],
      });
    } catch (err) {
      return failure(err);
    }
  },
);

async function main() {
  await server.connect(new StdioServerTransport());
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
