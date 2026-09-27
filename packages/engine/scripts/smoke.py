#!/usr/bin/env python3
"""End-to-end check against a running engine: design -> lock -> speak.

    uv run python scripts/smoke.py [--candidates 2] [--out out/smoke]

Exits non-zero if any job fails. Prints every output's checks.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from voice_engine.client import EngineClient

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def show(job: dict) -> None:
    print(f"\n{job['type']} {job['id']} -> {job['status']}  backend={job.get('backend')}")
    if job.get("error"):
        print(f"  error: {job['error']}")
    for out in job.get("outputs", []):
        c = out["checks"]
        flag = "ok" if c["ok"] else ",".join(c["warnings"])
        print(f"  {out['file']:18} {c['duration_s']:6.2f}s peak={c['peak']:.2f} rms={c['rms_dbfs']:.1f}dBFS  {flag}")


def run(client: EngineClient, spec: dict, out: Path) -> dict:
    job = client.wait(client.submit(spec)["id"])
    show(job)
    if job["status"] != "succeeded":
        sys.exit(1)
    client.download(job, out)
    return job


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", type=int, default=2)
    parser.add_argument("--out", default="out/smoke")
    parser.add_argument("--url")
    parser.add_argument("--token")
    args = parser.parse_args()

    client = EngineClient(args.url, args.token)
    print(json.dumps(client.health()))
    out = Path(args.out)

    design = json.loads((EXAMPLES / "design.json").read_text())
    design["candidates"] = args.candidates
    design_job = run(client, design, out)

    voice_id = f"smoke-{datetime.now():%Y%m%d-%H%M%S}"
    run(client, {"type": "lock", "voice_id": voice_id, "from_job": design_job["id"], "candidate": 1}, out)

    speak = json.loads((EXAMPLES / "speak.json").read_text())
    speak["voice_id"] = voice_id
    run(client, speak, out)

    print(f"\nall jobs succeeded. WAVs under {out.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
