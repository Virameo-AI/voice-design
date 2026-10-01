import { networkInterfaces } from "node:os";
import { resolve } from "node:path";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { WebStandardStreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/webStandardStreamableHttp.js";
import { VoiceClient } from "./client.ts";
import { registerTools } from "./tools.ts";

const INSTRUCTIONS =
  "Design a voice, preview the saved WAVs, lock one candidate, then speak. design_voice and preview_voice write candidate files under the output directory and return absolute paths. speak writes the finished WAV and returns its path for the next content step. Templates store voice recipes. The profile stores voices kept for reuse.";

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
