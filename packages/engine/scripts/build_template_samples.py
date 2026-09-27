#!/usr/bin/env python3
"""Generate one heard-before-you-try sample per built-in template.

Uses the studio that is already running, so the models stay loaded.
Writes packages/engine/src/voice_engine/catalog_samples/<id>.wav
and deletes the design jobs afterward.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages" / "engine" / "src"))

from voice_engine.catalog import CATALOG, PREVIEW, SAMPLE_DIR  # noqa: E402

BASE = "http://127.0.0.1:8180"


def request(method: str, path: str, body: dict | None = None) -> tuple[int, bytes]:
    data = None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def wait(job_id: str) -> dict:
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        status, raw = request("GET", f"/v1/jobs/{job_id}")
        if status != 200:
            raise SystemExit(f"{job_id} poll failed: {status} {raw[:200]!r}")
        job = json.loads(raw)
        if job["status"] in {"succeeded", "failed", "cancelled"}:
            return job
        time.sleep(0.4)
    raise SystemExit(f"{job_id} did not finish")


def main() -> None:
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    status, _ = request("GET", "/health")
    if status != 200:
        raise SystemExit(f"studio is not answering ({status})")
    for item in CATALOG:
        target = SAMPLE_DIR / f"{item.id}.wav"
        if target.is_file() and target.stat().st_size > 1000:
            print(f"keep {item.id}")
            continue
        status, raw = request(
            "POST",
            "/v1/jobs",
            {
                "type": "design",
                "instruct": item.instruct,
                "text": PREVIEW,
                "language": "English",
                "candidates": 1,
                "seed_start": item.seed_start,
                "params": {},
            },
        )
        if status != 202:
            raise SystemExit(f"{item.id} submit failed: {status} {raw[:300]!r}")
        job = wait(json.loads(raw)["id"])
        if job["status"] != "succeeded" or not job["outputs"]:
            raise SystemExit(f"{item.id} {job['status']}: {job.get('error')}")
        code, wav = request("GET", job["outputs"][0]["url"])
        if code != 200 or wav[:4] != b"RIFF":
            raise SystemExit(f"{item.id} download failed: {code}")
        target.write_bytes(wav)
        request("DELETE", f"/v1/jobs/{job['id']}/record")
        print(f"wrote {item.id} {len(wav)} bytes")


if __name__ == "__main__":
    main()
