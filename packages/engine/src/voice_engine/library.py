from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from voice_engine.backends.torch_backend import PROMPT_FILE

VOICE_FILES = {"master.wav", "preview.txt", "instruct.txt", "voice.json"}


class Library:
    """Locked voices and their versions, stored as database rows."""

    def __init__(self, storage) -> None:
        self.storage = storage

    def exists(self, voice_id: str) -> bool:
        return self.storage.voices.exists(voice_id)

    def get(self, voice_id: str) -> dict | None:
        voice = self.storage.voices.get(voice_id)
        if voice is None:
            return None
        voice["versions"] = self.storage.versions.list(voice_id)
        return voice

    def list(self, include_archived: bool = False) -> list[dict]:
        voices = self.storage.voices.list(include_archived)
        for voice in voices:
            voice["version_count"] = int(
                self.storage.query("SELECT COUNT(*) AS n FROM voice_versions WHERE voice_id = ?", (voice["voice_id"],))[0]["n"]
            )
        return voices

    def update(self, voice_id: str, **fields) -> dict:
        self.storage.voices.update(voice_id, **fields)
        return self.get(voice_id)

    def delete(self, voice_id: str) -> None:
        if not self.exists(voice_id):
            raise LookupError(voice_id)
        if self.storage.narrations.uses_voice(voice_id):
            raise PermissionError("narrations use this voice. Archive it instead, or delete those narrations first.")
        self.storage.voices.delete(voice_id)

    def resolve_version(self, voice_id: str, version_id: str | None) -> dict:
        """The version to speak with: the one asked for, or the voice's current one."""
        voice = self.storage.voices.get(voice_id)
        if voice is None:
            raise LookupError(f"voice {voice_id} not found")
        chosen = version_id or voice.get("current_version_id")
        if chosen is None:
            raise LookupError(f"voice {voice_id} has no versions")
        version = self.storage.versions.get(chosen)
        if version is None or version["voice_id"] != voice_id:
            raise LookupError(f"version {chosen} not found on voice {voice_id}")
        return version

    def file(self, voice_id: str, name: str) -> tuple[bytes, str] | None:
        if name not in VOICE_FILES or not self.exists(voice_id):
            return None
        if name == "master.wav":
            version = self.resolve_version(voice_id, None)
            wav = self.storage.versions.audio(version["id"])
            return (wav, "audio/wav") if wav is not None else None
        if name == "preview.txt":
            text = self.storage.voices.text(voice_id, "preview")
            return (text.encode(), "text/plain") if text is not None else None
        if name == "instruct.txt":
            text = self.storage.voices.text(voice_id, "instruct")
            return (text.encode(), "text/plain") if text is not None else None
        payload = json.dumps(self.get(voice_id), indent=2).encode()
        return payload, "application/json"

    def version_wav(self, voice_id: str, version_id: str) -> bytes | None:
        version = self.storage.versions.get(version_id)
        if version is None or version["voice_id"] != voice_id:
            return None
        return self.storage.versions.audio(version_id)

    def prepare_prompt(self, master_wav: bytes, ref_text: str, prepare) -> bytes | None:
        """Run the backend's lock step in a scratch folder and return the prompt bytes."""
        root = Path(tempfile.mkdtemp())
        folder = root / "voice"
        folder.mkdir()
        try:
            master = folder / "master.wav"
            master.write_bytes(master_wav)
            prepare(master, folder)
            prompt_path = folder / PROMPT_FILE
            return prompt_path.read_bytes() if prompt_path.is_file() else None
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def create(
        self,
        voice_id: str,
        source_wav: bytes,
        preview_text: str,
        instruct: str,
        meta: dict,
        prepare,
    ) -> dict:
        if self.exists(voice_id):
            raise FileExistsError(f"voice {voice_id} already exists. Use a new version id.")
        prompt = self.prepare_prompt(source_wav, preview_text, prepare)
        self.storage.voices.insert(
            {"voice_id": voice_id, **meta},
            preview_text.strip() + "\n",
            instruct.strip() + "\n",
            source_wav,
            prompt,
        )
        return self.storage.versions.add(
            voice_id,
            kind="original",
            audio=source_wav,
            sample_rate=meta["sample_rate"],
            ref_text=preview_text.strip(),
            duration_s=meta.get("duration_s"),
            prompt=prompt,
            job_id=meta.get("from_job"),
            label="Original",
        )

    def copy(self, source_id: str, voice_id: str, name: str | None, version_id: str | None, prepare) -> dict:
        source = self.storage.voices.get(source_id)
        if source is None:
            raise LookupError(f"voice {source_id} not found")
        if self.exists(voice_id):
            raise FileExistsError(f"voice {voice_id} already exists")
        version = self.resolve_version(source_id, version_id)
        wav = self.storage.versions.audio(version["id"])
        assert wav is not None
        meta = {
            **{k: source[k] for k in ("notes", "language", "from_job", "candidate", "seed", "design_backend", "sample_rate", "playground_id")},
            "voice_id": voice_id,
            "name": name or f"{source['name']} copy",
            "created_at": _now(),
            "copied_from": version["id"],
        }
        preview = self.storage.voices.text(source_id, "preview") or ""
        instruct = self.storage.voices.text(source_id, "instruct") or ""
        prompt = self.storage.versions.prompt(version["id"])
        self.storage.voices.insert(meta, preview, instruct, wav, prompt)
        self.storage.versions.add(
            voice_id,
            kind="original",
            audio=wav,
            sample_rate=version["sample_rate"],
            ref_text=version["ref_text"],
            duration_s=version.get("duration_s"),
            prompt=prompt,
            label=f"Copy of {version['id']}",
            edits=version.get("edits") or {},
        )
        return self.get(voice_id)

    def stage(self, voice_id: str, version_id: str | None = None):
        """A temporary folder the backend can read. Deleted when the call ends."""
        return _Stage(self, voice_id, version_id)


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class _Stage:
    def __init__(self, library: Library, voice_id: str, version_id: str | None) -> None:
        self.library = library
        self.voice_id = voice_id
        self.version_id = version_id
        self.root: Path | None = None
        self.folder: Path | None = None

    def __enter__(self) -> Path:
        version = self.library.resolve_version(self.voice_id, self.version_id)
        self.version_id = version["id"]
        self.root = Path(tempfile.mkdtemp())
        self.folder = self.root / self.voice_id
        self.folder.mkdir()
        master = self.library.storage.versions.audio(version["id"])
        if master is None:
            raise LookupError(f"voice {self.voice_id} has no audio")
        (self.folder / "master.wav").write_bytes(master)
        (self.folder / "preview.txt").write_text(version["ref_text"])
        prompt = self.library.storage.versions.prompt(version["id"])
        if prompt:
            (self.folder / PROMPT_FILE).write_bytes(prompt)
        return self.folder

    def __exit__(self, *_) -> None:
        if self.folder is not None and self.version_id is not None:
            prompt_path = self.folder / PROMPT_FILE
            if prompt_path.is_file():
                self.library.storage.versions.set_prompt(self.version_id, prompt_path.read_bytes())
        if self.root is not None:
            shutil.rmtree(self.root, ignore_errors=True)
