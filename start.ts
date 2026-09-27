// One entry point. Starts the voice engine on loopback, then the studio,
// which is the only address a browser uses.
import { join, resolve } from "node:path";

interface FileConfig {
  server?: { host?: string; port?: number; token?: string };
  engine?: { port?: number; backend?: string; data_dir?: string; preload?: boolean };
}

const root = import.meta.dir;
const dev = process.argv.includes("--dev");
const config = Bun.TOML.parse(await Bun.file(join(root, "voice-generator.toml")).text()) as FileConfig;

const host = config.server?.host ?? "127.0.0.1";
const port = Number(config.server?.port ?? 8180);
const token = config.server?.token ?? "";
const enginePort = Number(config.engine?.port ?? 8100);
const backend = config.engine?.backend ?? "auto";
// Relative to the repository root; an absolute path is used as is.
const dataDir = resolve(root, config.engine?.data_dir ?? "data");
const preload = config.engine?.preload ?? true;

if (!["127.0.0.1", "localhost", "::1"].includes(host) && !token) {
  console.error(`host ${host} is reachable from other machines. Set server.token in voice-generator.toml.`);
  process.exit(2);
}

const engine = Bun.spawn(
  [
    "uv",
    "run",
    "--project",
    join(root, "packages/engine"),
    "voice-engine",
    "serve",
    "--host",
    "127.0.0.1",
    "--port",
    String(enginePort),
    "--backend",
    backend,
    "--data-dir",
    dataDir,
    ...(preload ? ["--preload"] : []),
  ],
  { cwd: root, stdout: "inherit", stderr: "inherit" },
);

let studio: Bun.Subprocess | null = null;
let stopping = false;

function stop(code = 0): void {
  if (stopping) return;
  stopping = true;
  studio?.kill();
  engine.kill();
  process.exit(code);
}

process.on("SIGINT", () => stop(0));
process.on("SIGTERM", () => stop(0));

async function waitForEngine(): Promise<void> {
  const url = `http://127.0.0.1:${enginePort}/health`;
  for (let attempt = 0; attempt < 240; attempt++) {
    if (engine.exitCode !== null) throw new Error("the voice engine exited before it was ready");
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch {
      /* still starting */
    }
    await Bun.sleep(500);
  }
  throw new Error("the voice engine did not answer /health");
}

try {
  await waitForEngine();
} catch (err) {
  console.error(err instanceof Error ? err.message : err);
  stop(1);
}

const shown = host === "0.0.0.0" || host === "::" ? "127.0.0.1" : host;
console.log(`voice-generator  http://${shown}:${port}`);

studio = Bun.spawn(["bun", ...(dev ? ["--hot"] : []), "server.ts", ...(dev ? [] : ["--production"])], {
  cwd: join(root, "packages/studio"),
  stdout: "inherit",
  stderr: "inherit",
  env: {
    ...process.env,
    HOST: host,
    PORT: String(port),
    VOICE_ENGINE_URL: `http://127.0.0.1:${enginePort}`,
    VOICE_GENERATOR_TOKEN: token,
  },
});

const exitCode = await studio.exited;
stop(exitCode ?? 0);
