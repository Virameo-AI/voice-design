from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from voice_engine.backends.torch_backend import PROMPT_FILE

VOICE_FILES = {"master.wav", "preview.txt", "instruct.txt", "voice.json"}


class Library:
    """Locked voices stored as database rows."""

    def __init__(self, storage) -> None:
        self.storage = storage

    def exists(self, voice_id: str) -> bool:
        return self.storage.voices.exists(voice_id)

    def get(self, voice_id: str) -> dict | None:
        return self.storage.voices.get(voice_id)

    def list(self) -> list[dict]:
        return self.storage.voices.list()

    def delete(self, voice_id: str) -> None:
        if not self.storage.voices.delete(voice_id):
            raise LookupError(voice_id)

    def file(self, voice_id: str, name: str) -> tuple[bytes, str] | None:
        if name not in VOICE_FILES or not self.exists(voice_id):
            return None
        if name == "master.wav":
            wav = self.storage.voices.master_wav(voice_id)
            return (wav, "audio/wav") if wav is not None else None
        if name == "preview.txt":
            text = self.storage.voices.text(voice_id, "preview")
            return (text.encode(), "text/plain") if text is not None else None
        if name == "instruct.txt":
            text = self.storage.voices.text(voice_id, "instruct")
            return (text.encode(), "text/plain") if text is not None else None
        payload = json.dumps(self.get(voice_id), indent=2).encode()
        return payload, "application/json"

    def create(
        self,
        voice_id: str,
        source_wav: bytes,
        preview_text: str,
        instruct: str,
        meta: dict,
        prepare,
    ) -> None:
        if self.exists(voice_id):
            raise FileExistsError(f"voice {voice_id} already exists. Use a new version id.")
        root = Path(tempfile.mkdtemp())
        folder = root / voice_id
        folder.mkdir()
        try:
            master = folder / "master.wav"
            master.write_bytes(source_wav)
            prepare(master, folder)
            prompt_path = folder / PROMPT_FILE
            prompt = prompt_path.read_bytes() if prompt_path.is_file() else None
        finally:
            shutil.rmtree(root, ignore_errors=True)
        self.storage.voices.insert(
            {"voice_id": voice_id, **meta},
            preview_text.strip() + "\n",
            instruct.strip() + "\n",
            source_wav,
            prompt,
        )

    def stage(self, voice_id: str):
        """A temporary folder the backend can read. Deleted when the call ends."""
        return _Stage(self, voice_id)


class _Stage:
    def __init__(self, library: Library, voice_id: str) -> None:
        self.library = library
        self.voice_id = voice_id
        self.root: Path | None = None
        self.folder: Path | None = None

    def __enter__(self) -> Path:
        if not self.library.exists(self.voice_id):
            raise LookupError(f"voice {self.voice_id} not found")
        self.root = Path(tempfile.mkdtemp())
        self.folder = self.root / self.voice_id
        self.folder.mkdir()
        master = self.library.storage.voices.master_wav(self.voice_id)
        if master is None:
            raise LookupError(f"voice {self.voice_id} not found")
        (self.folder / "master.wav").write_bytes(master)
        preview = self.library.storage.voices.text(self.voice_id, "preview") or ""
        (self.folder / "preview.txt").write_text(preview)
        prompt = self.library.storage.voices.prompt(self.voice_id)
        if prompt:
            (self.folder / PROMPT_FILE).write_bytes(prompt)
        return self.folder

    def __exit__(self, *_) -> None:
        if self.folder is not None:
            prompt_path = self.folder / PROMPT_FILE
            if prompt_path.is_file():
                self.library.storage.voices.set_prompt(self.voice_id, prompt_path.read_bytes())
        if self.root is not None:
            shutil.rmtree(self.root, ignore_errors=True)
