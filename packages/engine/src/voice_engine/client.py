from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import httpx

TERMINAL = {"succeeded", "failed", "cancelled"}


class EngineClient:
    """Small HTTP client for the voice-engine service."""

    def __init__(self, url: str | None = None, token: str | None = None, timeout: float = 30) -> None:
        url = url or os.environ.get("VOICE_ENGINE_URL", "http://127.0.0.1:8100")
        token = token or os.environ.get("VOICE_ENGINE_TOKEN")
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        self.http = httpx.Client(base_url=url.rstrip("/"), headers=headers, timeout=timeout)

    def _json(self, response: httpx.Response):
        if response.is_error:
            raise RuntimeError(f"{response.status_code} {response.request.url.path}: {response.text}")
        return response.json()

    def health(self) -> dict:
        return self._json(self.http.get("/health"))

    def submit(self, spec: dict) -> dict:
        return self._json(self.http.post("/v1/jobs", json=spec))

    def job(self, job_id: str) -> dict:
        return self._json(self.http.get(f"/v1/jobs/{job_id}"))

    def voices(self) -> list[dict]:
        return self._json(self.http.get("/v1/voices"))

    def wait(self, job_id: str, timeout: float = 1800, interval: float = 2, quiet: bool = False) -> dict:
        deadline = time.monotonic() + timeout
        seen = -1
        while True:
            job = self.job(job_id)
            done = len(job.get("outputs", []))
            if not quiet and (done != seen):
                print(f"{job_id} {job['status']} outputs={done}", file=sys.stderr)
                seen = done
            if job["status"] in TERMINAL:
                return job
            if time.monotonic() > deadline:
                raise TimeoutError(f"{job_id} still {job['status']} after {timeout}s")
            time.sleep(interval)

    def download(self, job: dict, out_dir: Path) -> list[Path]:
        folder = out_dir / job["id"]
        folder.mkdir(parents=True, exist_ok=True)
        paths = []
        for output in job.get("outputs", []):
            response = self.http.get(f"/v1/jobs/{job['id']}/files/{output['file']}")
            if response.is_error:
                raise RuntimeError(f"{response.status_code} downloading {output['file']}")
            path = folder / output["file"]
            path.write_bytes(response.content)
            paths.append(path)
        return paths
