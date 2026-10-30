"""Serve revision-pinned builds on loopback, with input-staleness reporting."""

import html
import json
import mimetypes
import re
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .build import build_project
from .environment import file_hash, read_json
from .project import InputError, input_identity


def catalog_projects(root: Path) -> list[dict]:
    entries = []
    projects = (root / "projects").resolve()
    for path in sorted(projects.iterdir()):
        try:
            resolved = path.resolve()
        except (OSError, RuntimeError):
            continue
        if (
            not resolved.is_relative_to(projects)
            or not resolved.is_dir()
            or not (resolved / "project.py").is_file()
        ):
            continue
        slug = path.name
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug):
            continue
        metadata = {}
        metadata_path = resolved / "preview.json"
        if metadata_path.is_file():
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                metadata = {}
        kind = metadata.get("kind") if isinstance(metadata, dict) else None
        title = metadata.get("title") if isinstance(metadata, dict) else None
        if kind not in {"design", "example"}:
            kind = "example"
        entries.append(
            {
                "name": slug,
                "title": title
                if isinstance(title, str)
                else slug.replace("-", " ").title(),
                "kind": kind,
                "path": resolved,
            }
        )
    return sorted(entries, key=lambda item: (item["kind"] != "design", item["name"]))


def ensure_current_build(root: Path, project_path: Path) -> tuple[Path, dict]:
    try:
        directory, manifest = latest_build(project_path)
        status = input_status(project_path, manifest["input_identity"])
        if status["status"] == "current":
            return directory, manifest
    except (InputError, KeyError, TypeError):
        pass
    build_project(root, project_path)
    return latest_build(project_path)


def _catalog_html(entries: list[dict]) -> bytes:
    sections = []
    for kind, label in (("design", "Designs"), ("example", "Examples and tests")):
        rows = []
        for entry in (item for item in entries if item["kind"] == kind):
            title = html.escape(entry["title"])
            slug = entry["name"]
            try:
                _, manifest = latest_build(entry["path"])
                state = input_status(entry["path"], manifest["input_identity"])[
                    "status"
                ]
                links = " · ".join(
                    f'<a href="/designs/{slug}/{page}.html">{name}</a>'
                    for page, name in (
                        ("preview", "Preview"),
                        ("report", "Report"),
                        ("assembly", "Assembly"),
                    )
                    if page + ".html" in manifest.get("files", {})
                )
                detail = f"{html.escape(state)} build · {links or 'No viewer pages'}"
            except (InputError, OSError, ValueError, KeyError, TypeError):
                detail = "No captured build"
            rows.append(
                f"<li><strong>{title}</strong> <code>{html.escape(slug)}</code>"
                f"<br>{detail}</li>"
            )
        sections.append(f"<h2>{label}</h2><ul>{''.join(rows)}</ul>")
    page = (
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>Buratino preview catalog</title><style>"
        "body{font:16px/1.55 system-ui;max-width:900px;margin:40px auto;padding:0 24px;"
        "color:#243233;background:#fafaf7}li{padding:10px 0}a{color:#226458}"
        "</style><body><h1>Buratino projects</h1>"
        "<p>Captured builds are drafts, not manufacturing packages.</p>"
        + "".join(sections)
        + "</body></html>"
    )
    return page.encode()


def _catalog_project_route(relative: str, projects: dict[str, Path]):
    parts = relative.split("/")
    if len(parts) < 3 or parts[0] != "designs" or parts[1] not in projects:
        return None
    return projects[parts[1]].resolve(), "/".join(parts[2:])


def _build(project_path: Path, revision: str | None = None) -> tuple[Path, dict]:
    builds = project_path.resolve() / "build"
    try:
        if revision is None:
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


def latest_build(project_path: Path) -> tuple[Path, dict]:
    return _build(project_path)


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


def preview_server(
    project_path: Path, port: int = 0, *, catalog_root: Path | None = None
) -> ThreadingHTTPServer:
    # Validate the initial build before starting the server, as before.
    if catalog_root is None:
        initial_directory, initial_manifest = latest_build(project_path)
        builds = {
            (project_path.resolve(), initial_manifest["revision"]): (
                initial_directory,
                initial_manifest,
            )
        }
        entries = []
        projects_by_name = {}
    else:
        entries = catalog_projects(catalog_root)
        projects_by_name = {item["name"]: item["path"] for item in entries}
        builds = {}
    public_files = {
        "preview.html",
        "report.html",
        "assembly.html",
        "result.json",
        "parts.csv",
        "cabinet.glb",
    }

    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def send_head(self):
            raw_path = urlsplit(self.path).path
            try:
                relative = unquote(raw_path, errors="strict").lstrip("/")
            except (UnicodeDecodeError, ValueError):
                self.send_error(404)
                return None
            if (
                (not relative and catalog_root is None)
                or "\\" in relative
                or (
                    relative
                    and any(part in {"", ".", ".."} for part in relative.split("/"))
                )
            ):
                self.send_error(404)
                return None

            selected_project = project_path.resolve()
            selected_name = None
            if catalog_root is not None:
                if relative in {"", "index.html"}:
                    data = _catalog_html(entries)
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    if self.command != "HEAD":
                        self.wfile.write(data)
                    return None
                route = _catalog_project_route(relative, projects_by_name)
                if route is None:
                    self.send_error(404)
                    return None
                selected_name = relative.split("/")[1]
                selected_project, relative = route

            parts = relative.split("/")
            pinned = parts[0] == "revisions" and len(parts) >= 3
            try:
                revision = (
                    parts[1]
                    if pinned
                    else read_json(selected_project / "build" / "latest.json")[
                        "revision"
                    ]
                )
                build_key = (selected_project, revision)
                if build_key not in builds:
                    builds[build_key] = _build(selected_project, revision)
                directory, manifest = builds[build_key]
                if pinned:
                    relative = "/".join(parts[2:])
            except (InputError, OSError, ValueError, KeyError, TypeError):
                self.send_error(404)
                return None

            if relative == "status.json":
                data = json.dumps(
                    input_status(selected_project, manifest["input_identity"])
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(data)
                return None

            listed_files = set(manifest["files"])
            allowed = (public_files & listed_files) | {
                name for name in listed_files if name.startswith("assets/")
            }
            if relative not in allowed:
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
            if not pinned and relative in {
                "preview.html",
                "report.html",
                "assembly.html",
            }:
                data = stream.read()
                stream.close()
                base_path = (
                    f"/designs/{selected_name}/revisions/{manifest['revision']}/"
                    if selected_name is not None
                    else f"/revisions/{manifest['revision']}/"
                )
                base = f'<base href="{base_path}">'.encode()
                data = re.sub(
                    rb"<html\b[^>]*>",
                    lambda match: match.group() + base,
                    data,
                    count=1,
                    flags=re.IGNORECASE,
                )
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(data)
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
        ("127.0.0.1", port), partial(Handler, directory=str(project_path))
    )


def preview_catalog_server(root: Path, port: int = 0) -> ThreadingHTTPServer:
    return preview_server(root / "projects", port, catalog_root=root)
