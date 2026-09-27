from __future__ import annotations

import argparse
import json
import logging
import platform
import sys
from pathlib import Path


def _print(data) -> None:
    print(json.dumps(data, indent=2))


def cmd_serve(args) -> int:
    import uvicorn

    from voice_engine.app import create_app
    from voice_engine.config import load_settings

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    try:
        settings = load_settings(
            Path(args.config) if args.config else None,
            host=args.host,
            port=args.port,
            backend=args.backend,
            data_dir=args.data_dir,
            preload=True if args.preload else None,
        )
    except ValueError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2
    app = create_app(settings)
    docs_host = "127.0.0.1" if settings.host in {"0.0.0.0", "::"} else settings.host
    print(f"voice-engine listening on {settings.host}:{settings.port}", file=sys.stderr)
    print(f"swagger  http://{docs_host}:{settings.port}/docs", file=sys.stderr)
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="info")
    return 0


def cmd_doctor(_args) -> int:
    from voice_engine.backends import detect

    backend = detect()
    print(f"os={platform.system()} {platform.release()} machine={platform.machine()}")
    print(f"python={platform.python_version()}")
    print(f"backend={backend or 'none'}")
    if sys.version_info[:2] != (3, 12):
        print("warning=use Python 3.12")
    if backend == "mlx":
        try:
            import mlx_audio  # noqa: F401
        except ImportError:
            print("mlx_audio=missing  fix: uv sync --extra mac")
            return 1
        print("mlx_audio=installed")
        return 0
    if backend == "cuda":
        import torch

        try:
            import qwen_tts  # noqa: F401
        except ImportError:
            print("qwen_tts=missing  fix: uv sync --extra cuda")
            return 1
        print(f"torch={torch.__version__} gpu={torch.cuda.get_device_name(0)}")
        return 0
    if backend == "cpu":
        import torch

        print(f"torch={torch.__version__} gpu=none threads={torch.get_num_threads()}")
        print("cpu=ok  the models run on the CPU in float32. Slow, and about 14 GB of RAM for both models.")
        return 0
    print("no GPU, and the CPU model libraries are not installed.")
    print("fix: uv sync --extra cpu   (or --extra cuda on NVIDIA). --backend fake runs without models.")
    return 1


def _client(args):
    from voice_engine.client import EngineClient

    return EngineClient(args.url, args.token)


def cmd_submit(args) -> int:
    raw = sys.stdin.read() if args.spec == "-" else Path(args.spec).read_text()
    spec = json.loads(raw)
    for item in args.set or []:
        key, _, value = item.partition("=")
        try:
            spec[key] = json.loads(value)
        except json.JSONDecodeError:
            spec[key] = value
    client = _client(args)
    job = client.submit(spec)
    if args.wait or args.download:
        job = client.wait(job["id"], timeout=args.timeout)
        if args.download and job["status"] == "succeeded":
            for path in client.download(job, Path(args.download)):
                print(f"saved {path}", file=sys.stderr)
    _print(job)
    return 1 if job["status"] in {"failed", "cancelled"} else 0


def cmd_status(args) -> int:
    client = _client(args)
    job = client.wait(args.job_id, timeout=args.timeout) if args.wait else client.job(args.job_id)
    _print(job)
    return 1 if job["status"] == "failed" else 0


def cmd_fetch(args) -> int:
    client = _client(args)
    for path in client.download(client.job(args.job_id), Path(args.out)):
        print(path)
    return 0


def cmd_voices(args) -> int:
    _print(_client(args).voices())
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="voice-engine", description="Voice design and speech service")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="Run the HTTP service")
    serve.add_argument("--config", help="path to engine.toml")
    serve.add_argument("--host")
    serve.add_argument("--port", type=int)
    serve.add_argument("--backend", choices=["auto", "mlx", "cuda", "cpu", "fake"])
    serve.add_argument("--data-dir")
    serve.add_argument("--preload", action="store_true", help="load models at startup")
    serve.set_defaults(func=cmd_serve)

    doctor = sub.add_parser("doctor", help="Show which backend this machine can use")
    doctor.set_defaults(func=cmd_doctor)

    def client_opts(p):
        p.add_argument("--url", help="default $VOICE_ENGINE_URL or http://127.0.0.1:8100")
        p.add_argument("--token", help="default $VOICE_ENGINE_TOKEN")

    submit = sub.add_parser("submit", help="Submit a job spec (JSON file or - for stdin)")
    submit.add_argument("spec")
    submit.add_argument("--set", action="append", metavar="KEY=VALUE", help="override a top-level field")
    submit.add_argument("--wait", action="store_true")
    submit.add_argument("--download", metavar="DIR", help="wait, then save outputs to DIR/<job_id>/")
    submit.add_argument("--timeout", type=float, default=1800)
    client_opts(submit)
    submit.set_defaults(func=cmd_submit)

    status = sub.add_parser("status", help="Show a job")
    status.add_argument("job_id")
    status.add_argument("--wait", action="store_true")
    status.add_argument("--timeout", type=float, default=1800)
    client_opts(status)
    status.set_defaults(func=cmd_status)

    fetch = sub.add_parser("fetch", help="Download a job's WAVs")
    fetch.add_argument("job_id")
    fetch.add_argument("--out", default="out")
    client_opts(fetch)
    fetch.set_defaults(func=cmd_fetch)

    voices = sub.add_parser("voices", help="List locked voices")
    client_opts(voices)
    voices.set_defaults(func=cmd_voices)
    return parser


def main(argv: list[str] | None = None) -> int:
    import httpx

    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except httpx.ConnectError as exc:
        print(f"error: cannot reach the engine ({exc}). Is `voice-engine serve` running?", file=sys.stderr)
        return 1
    except (RuntimeError, TimeoutError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
