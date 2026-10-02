import { expect, test } from "bun:test";
import { handleMcp } from "../src/http.ts";
import { TOOL_NAMES } from "../src/tools.ts";

async function rpc(method: string, params: Record<string, unknown>, id: number) {
  const response = await handleMcp(
    new Request("http://127.0.0.1/mcp", {
      method: "POST",
      headers: { "content-type": "application/json", accept: "application/json, text/event-stream" },
      body: JSON.stringify({ jsonrpc: "2.0", id, method, params }),
    }),
  );
  return (await response.json()) as { result?: any; error?: any };
}

test("tools/list exposes every tool with a description an agent can act on", async () => {
  const body = await rpc("tools/list", {}, 2);
  const tools = body.result?.tools as Array<{ name: string; description: string; inputSchema: unknown }>;
  expect(tools.map((tool) => tool.name).sort()).toEqual([...TOOL_NAMES].sort());
  for (const tool of tools) {
    expect(tool.description.length).toBeGreaterThan(20);
  }
  const render = tools.find((tool) => tool.name === "render_saved_narration")!;
  expect(render.description).toContain("get_job");
});

test("a tool call against a stopped engine returns a readable error instead of throwing", async () => {
  process.env.VOICE_ENGINE_URL = "http://127.0.0.1:9";
  const body = await rpc("tools/call", { name: "list_styles", arguments: {} }, 3);
  expect(body.result?.isError).toBe(true);
  expect(body.result?.content?.[0]?.text).toContain("unreachable");
});
