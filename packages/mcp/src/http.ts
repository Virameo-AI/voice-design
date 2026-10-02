import { networkInterfaces } from "node:os";
import { resolve } from "node:path";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { WebStandardStreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/webStandardStreamableHttp.js";
import { VoiceClient } from "./client.ts";
import { registerTools } from "./tools.ts";

const INSTRUCTIONS =
  "Flow: create_playground (or design_voice) → run_playground → get_job until succeeded → lock_voice → create_narration → render_saved_narration → get_job → download_narration. Long jobs return immediately with a job id; poll get_job about every 15 seconds and read next for what to do. Tool results carry file paths, never audio bytes. A locked voice is version 1 (narrator@1); narrations freeze the version they used. list_downloads shows every WAV that can be written to disk.";

export function lanAddress(): string {
  for (const entries of Object.values(networkInterfaces())) {
    for (const entry of entries ?? []) {
      if (entry.family === "IPv4" && !entry.internal) return entry.address;
    }
  }
  return "127.0.0.1";
}

export function buildServer(): McpServer {
  const engine = (process.env.VOICE_ENGINE_URL ?? "http://127.0.0.1:8100").replace(/\/+$/, "");
  const outDir = resolve(process.env.VOICE_DESIGN_OUT ?? process.env.VOICE_GENERATOR_OUT ?? "data/out");
  const server = new McpServer({ name: "voice-design", version: "0.1.0" }, { instructions: INSTRUCTIONS });
  registerTools(server, new VoiceClient(engine, process.env.VOICE_ENGINE_TOKEN ?? ""), outDir);
  return server;
}

export async function handleMcp(request: Request): Promise<Response> {
  const server = buildServer();
  const transport = new WebStandardStreamableHTTPServerTransport({
    sessionIdGenerator: undefined,
    enableJsonResponse: true,
  });
  await server.connect(transport);
  try {
    return await transport.handleRequest(request);
  } finally {
    await transport.close();
    await server.close();
  }
}
