"""Serve one captured build on loopback, with input-staleness reporting."""

import json
import mimetypes
import re
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .environment import file_hash, read_json
from .project import InputError, input_identity


def latest_build(project_path: Path) -> tuple[Path, dict]:
    builds = project_path.resolve() / "build"
    try:
        revision = read_json(builds / "latest.json")["revision"]
        if not isinstance(revision, str) or not re.fullmatch(
            r"[a-f0-9]{12}-[a-f0-9]{8}", revision
        ):
            raise ValueError("Invalid build revision.")
        directory = (builds / revision).resolve()
        if directory.parent != builds:
            raise ValueError("Build is outside its project.")
        manifest = read_json(directory / "manifest.json")
        if manifest["revision"] != revision or manifest["status"] != "draft":
            raise ValueError("Build manifest and revision disagree.")
        for name, digest in manifest["files"].items():
            file = (directory / name).resolve()
            if (
                not file.is_relative_to(directory)
                or not file.is_file()
                or file_hash(file) != digest
            ):
                raise ValueError(f"Build file was changed or is missing: {name}")
        return directory, manifest
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise InputError("build_unavailable", f"Run build first. {exc}") from exc


def input_status(project_path: Path, expected_identity: str) -> dict:
    source = project_path.resolve() / "project.py"
    if not source.exists():
        if (project_path / "survey.json").is_file() or (
            project_path / "design.json"
        ).is_file():
            return {"status": "legacy"}
        return {"status": "unavailable", "error": "project.py is missing."}
    try:
        current = input_identity(project_path)
        return {"status": "current" if current == expected_identity else "stale"}
    except InputError as exc:
        return {"status": "unavailable", "error": str(exc)}


def preview_server(project_path: Path, port: int = 0) -> ThreadingHTTPServer:
    directory, manifest = latest_build(project_path)
    listed_files = set(manifest["files"])
    public_files = {
        "preview.html",
        "report.html",
        "assembly.html",
        "result.json",
        "parts.csv",
        "cabinet.glb",
    }
    allowed = (public_files & listed_files) | {
        name for name in listed_files if name.startswith("assets/")
    }

    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def _status(self, *, head_only: bool) -> None:
            data = json.dumps(
                input_status(project_path, manifest["input_identity"])
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if not head_only:
                self.wfile.write(data)

        def do_GET(self):  # noqa: N802
            if urlsplit(self.path).path == "/status.json":
                self._status(head_only=False)
                return
            super().do_GET()

        def do_HEAD(self):  # noqa: N802
            if urlsplit(self.path).path == "/status.json":
                self._status(head_only=True)
                return
            super().do_HEAD()

        def send_head(self):
            raw_path = urlsplit(self.path).path
            try:
                relative = unquote(raw_path, errors="strict").lstrip("/")
            except (UnicodeDecodeError, ValueError):
                self.send_error(404)
                return None
            if (
                not relative
                or "\\" in relative
                or any(part in {"", ".", ".."} for part in relative.split("/"))
                or relative not in allowed
            ):
                self.send_error(404)
                return None
            target = (directory / relative).resolve()
            if not target.is_relative_to(directory) or not target.is_file():
                self.send_error(404)
                return None
            try:
                stream = target.open("rb")
            except OSError:
                self.send_error(404)
                return None
            self.send_response(200)
            content_type = (
                mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            )
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(target.stat().st_size))
            self.end_headers()
            return stream

    return ThreadingHTTPServer(
        ("127.0.0.1", port), partial(Handler, directory=str(directory))
    )
