// The only HTTP server a browser talks to. It serves the UI and forwards the
// voice API to the engine on this machine.
import { timingSafeEqual } from "node:crypto";
import { handleMcp, lanAddress } from "../mcp/src/http.ts";
import index from "./index.html";

const ENGINE = (process.env.VOICE_ENGINE_URL ?? "http://127.0.0.1:8100").replace(/\/+$/, "");
const TOKEN = process.env.VOICE_GENERATOR_TOKEN ?? "";
const production = process.argv.includes("--production");

function authorized(req: Request): boolean {
  if (!TOKEN) return true;
  const got = Buffer.from(req.headers.get("authorization") ?? "");
  const expected = Buffer.from(`Bearer ${TOKEN}`);
  return got.length === expected.length && timingSafeEqual(got, expected);
}

async function mcp(req: Request): Promise<Response> {
  if (!authorized(req)) {
    return Response.json({ detail: "missing or wrong bearer token" }, { status: 401, headers: { "WWW-Authenticate": "Bearer" } });
  }
  return handleMcp(req);
}

async function proxy(req: Request): Promise<Response> {
  if (!authorized(req)) {
    return Response.json({ detail: "missing or wrong bearer token" }, { status: 401, headers: { "WWW-Authenticate": "Bearer" } });
  }
  const url = new URL(req.url);
  const headers = new Headers(req.headers);
  headers.delete("host");
  headers.delete("authorization");
  const hasBody = req.method !== "GET" && req.method !== "HEAD";
  try {
    const upstream = await fetch(ENGINE + url.pathname + url.search, {
      method: req.method,
      headers,
      body: hasBody ? await req.arrayBuffer() : undefined,
    });
    const out = new Headers(upstream.headers);
    out.delete("content-encoding");
    out.delete("content-length");
    return new Response(upstream.body, { status: upstream.status, headers: out });
  } catch {
    return Response.json({ detail: "voice engine is not running" }, { status: 502 });
  }
}

const server = Bun.serve({
  port: Number(process.env.PORT ?? 8180),
  hostname: process.env.HOST ?? "127.0.0.1",
  development: !production,
  routes: {
    "/health": proxy,
    "/mcp": mcp,
    "/mcp/": mcp,
    "/openapi.json": proxy,
    "/docs": proxy,
    "/docs/*": proxy,
    "/redoc": proxy,
    "/v1/*": proxy,
    "/*": index,
  },
});

const host = process.env.HOST ?? "127.0.0.1";
const advertised = host === "0.0.0.0" || host === "::" ? lanAddress() : host;
console.log(`voice-generator studio on ${server.url}`);
console.log(`voice-design  http://${advertised}:${server.port}/mcp`);
