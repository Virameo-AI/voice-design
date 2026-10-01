import { expect, test } from "bun:test";
import { handleMcp } from "../src/http.ts";

test("voice-design answers MCP initialize over HTTP", async () => {
  const response = await handleMcp(
    new Request("http://127.0.0.1/mcp", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        accept: "application/json, text/event-stream",
      },
      body: JSON.stringify({
        jsonrpc: "2.0",
        id: 1,
        method: "initialize",
        params: {
          protocolVersion: "2025-03-26",
          capabilities: {},
          clientInfo: { name: "test", version: "0.0.1" },
        },
      }),
    }),
  );
  expect(response.status).toBe(200);
  const body = (await response.json()) as { result?: { serverInfo?: { name?: string } } };
  expect(body.result?.serverInfo?.name).toBe("voice-design");
});
