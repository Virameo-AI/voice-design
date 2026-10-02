// One command. Installs the engine for this machine and downloads the Qwen weights.
import { spawn } from "node:child_process";

const root = import.meta.dir;
const arg = process.argv.find((item) => item.startsWith("--backend="))?.split("=")[1];
const darwinArm = process.platform === "darwin" && process.arch === "arm64";
const nvidia = Bun.which("nvidia-smi") != null;
const backend = arg ?? (darwinArm ? "mlx" : nvidia ? "cuda" : "cpu");
const extra = backend === "mlx" ? "mac" : backend;

function run(args: string[]): Promise<number> {
  return new Promise((resolve) => {
    const child = spawn(args[0], args.slice(1), { cwd: root, stdio: "inherit" });
    child.on("exit", (code) => resolve(code ?? 1));
  });
}

console.log(`voice-design setup  backend=${backend} extra=${extra}`);
const synced = await run(["uv", "sync", "--project", "packages/engine", "--extra", extra]);
if (synced !== 0) process.exit(synced);
const downloaded = await run([
  "uv", "run", "--project", "packages/engine", "--extra", extra,
  "voice-engine", "setup", "--backend", backend,
]);
process.exit(downloaded);
