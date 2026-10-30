"""Serve immutable drafts and rebuild changed inputs in background workers."""

import html
import json
import mimetypes
import os
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import suppress
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .build import build_project
from .environment import file_hash, read_json
from .project import InputError, _runtime_root, input_identity

# Served independently of captured assets, so older drafts can also refresh.
_REFRESH_SCRIPT = r"""
<script>
(() => {
  window.buratinoPreviewRefresh = true;
  const preview = document.querySelector('meta[name="buratino-preview"]');
  let navigating = false;
  async function refresh() {
    if (navigating) return;
    let banner = document.getElementById('draft-badge')
      || document.getElementById('buratino-preview-status');
    if (!banner) {
      banner = document.createElement('div');
      banner.id = 'buratino-preview-status';
      banner.style.cssText = 'position:fixed;top:12px;left:12px;z-index:10000;'
        + 'max-width:80vw;padding:8px 12px;background:#fff3cd;color:#3d3520;'
        + 'border:1px solid #d4bd76;border-radius:6px;font:14px system-ui';
      document.body.appendChild(banner);
    }
    try {
      const response = await fetch('./status.json', {cache: 'no-store'});
      if (!response.ok) throw new Error('Preview status unavailable');
      const {status, revision, error} = await response.json();
      if (revision && revision !== preview.content) {
        navigating = true;
        window.location.replace(preview.dataset.entry
          + window.location.search + window.location.hash);
        return;
      }
      banner.dataset.state = status;
      banner.title = error || '';
      banner.hidden = status === 'current';
      banner.textContent = status === 'updating' ? 'Updating draft…'
        : status === 'invalid' ? 'Invalid inputs · old draft'
          : status === 'stale' ? 'Stale inputs · old draft'
            : status === 'unavailable' ? 'Inputs unavailable' : '';
      if (error) banner.textContent += ' · ' + error;
    } catch {
      banner.hidden = false;
      banner.dataset.state = 'unavailable';
      banner.textContent = 'Preview status unavailable';
    }
    setTimeout(refresh, 1000);
  }
  document.addEventListener('DOMContentLoaded', refresh, {once: true});
})();
</script>
"""


def _signal_group(pid: int, sig: int):
    with suppress(ProcessLookupError):
        os.killpg(pid, sig)


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


def _catalog_html(entries: list[dict], states: dict | None = None) -> bytes:
    sections = []
    for kind, label in (("design", "Designs"), ("example", "Examples and tests")):
        rows = []
        for entry in (item for item in entries if item["kind"] == kind):
            title = html.escape(entry["title"])
            slug = entry["name"]
            try:
                if states is None:
                    _, manifest = latest_build(entry["path"])
                    state = input_status(entry["path"], manifest["input_identity"])[
                        "status"
                    ]
                    files = manifest.get("files", {})
                else:
                    state = states.get(slug, {}).get("status", "Open to watch inputs")
                    files = {"preview.html", "report.html", "assembly.html"}
                links = " · ".join(
                    f'<a href="/designs/{slug}/{page}.html">{name}</a>'
                    for page, name in (
                        ("preview", "Preview"),
                        ("report", "Report"),
                        ("assembly", "Assembly"),
                    )
                    if page + ".html" in files
                )
                detail = f"{html.escape(state)} build · {links or 'No viewer pages'}"
            except (InputError, OSError, ValueError, KeyError, TypeError):
                state = states.get(entry["name"], {}) if states else {}
                detail = (
                    f"{html.escape(state.get('status', 'No captured build'))} · "
                    f'<a href="/designs/{slug}/preview.html">Preview</a>'
                )
            if states and states.get(slug, {}).get("error"):
                detail += " · " + html.escape(states[slug]["error"])
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


class ProjectWatcher:
    """One serialized build loop. Failed input identities wait for a new edit."""

    def __init__(self, root: Path, project: Path, *, poll=0.25, debounce=0.6):
        self.root, self.project = root, project
        self.poll, self.debounce = poll, debounce
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.state = {"status": "updating", "revision": None}
        self.identity = None
        self.manifest = None
        try:
            _, self.manifest = latest_build(project)
            self.state = {"status": "current", "revision": self.manifest["revision"]}
        except InputError:
            pass
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def status(self, expected=None):
        with self.lock:
            value = dict(self.state)
            if value["status"] == "current" and expected and expected != self.identity:
                value["status"] = "stale"
            return value

    def _state(self, status, error=None):
        with self.lock:
            self.state = {
                "status": status,
                "revision": self.manifest["revision"] if self.manifest else None,
            }
            if error:
                self.state["error"] = str(error)

    def _build(self):
        # A fresh interpreter reloads changed engine rules and isolates CAD state.
        script = """
import json, sys
from pathlib import Path
from buratino.build import build_project
try:
    build_project(Path(sys.argv[1]), Path(sys.argv[2]), expected_identity=sys.argv[3])
except Exception as exc:
    print(json.dumps({"code": getattr(exc, "code", "build_failed"), "error": str(exc)}))
    sys.exit(1)
"""
        environment = dict(os.environ, BURATINO_ROOT=str(self.root))
        with tempfile.TemporaryFile(mode="w+") as output:
            child = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    script,
                    str(self.root),
                    str(self.project),
                    self.identity,
                ],
                stdout=output,
                stderr=output,
                env=environment,
                start_new_session=True,
            )
            try:
                while child.poll() is None:
                    if self.stop.wait(self.poll):
                        _signal_group(child.pid, signal.SIGTERM)
                        with suppress(subprocess.TimeoutExpired):
                            child.wait(timeout=5)
                        raise InputError("build_stopped", "Preview stopped.")
                if child.returncode:
                    output.seek(0)
                    message = output.read()
                    try:
                        failure = json.loads(message.strip().splitlines()[-1])
                    except (ValueError, IndexError):
                        failure = {"code": "build_failed", "error": message[-2000:]}
                    raise InputError(failure["code"], failure["error"])
            finally:
                # The leader can exit before a descendant which ignores TERM.
                _signal_group(child.pid, signal.SIGKILL)
                if child.poll() is None:
                    child.wait()
                # Remove only a lock owned by our terminated child.
                lock = self.project / "build/.lock"
                try:
                    if lock.read_text() == str(child.pid):
                        lock.unlink()
                except OSError:
                    pass

    def _run(self):
        observed = attempted = None
        changed_at = 0.0
        busy_attempts = 0
        retry_at = 0.0
        waiting_lock = False
        while not self.stop.is_set():
            try:
                identity = input_identity(self.project)
                # Also adopt builds published by the CLI or another preview server.
                pointer = (
                    read_json(self.project / "build/latest.json")
                    if (self.project / "build/latest.json").is_file()
                    else {}
                )
                if pointer.get("revision") != (
                    self.manifest["revision"] if self.manifest else None
                ) and pointer.get("revision"):
                    _, self.manifest = latest_build(self.project)
                self.identity = identity
                now = time.monotonic()
                if identity != observed:
                    observed, changed_at = identity, now
                    attempted = None
                    busy_attempts, retry_at, waiting_lock = 0, 0.0, False
                if self.manifest and identity == self.manifest["input_identity"]:
                    self._state("current")
                elif identity != attempted or waiting_lock:
                    lock_exists = (self.project / "build/.lock").exists()
                    if waiting_lock and busy_attempts >= 4 and lock_exists:
                        pass
                    elif now >= max(changed_at + self.debounce, retry_at):
                        if self.stop.is_set():
                            break
                        self._state("updating")
                        attempted = identity
                        try:
                            self._build()
                            _, self.manifest = latest_build(self.project)
                            waiting_lock = False
                            self._state("current")
                        except InputError as exc:
                            waiting_lock = exc.code == "build_busy"
                            busy_attempts += int(waiting_lock)
                            retry_at = now + min(0.5 * 2**busy_attempts, 4)
                            self._state("stale" if waiting_lock else "invalid", exc)
                        except Exception as exc:
                            self._state("invalid", exc)
                    elif not waiting_lock:
                        self._state("updating")
            except (InputError, OSError, ValueError, KeyError, TypeError) as exc:
                self._state("unavailable", exc)
            self.stop.wait(self.poll)

    def close(self):
        self.stop.set()
        # The child observes stop and is terminated within its bounded grace period.
        self.thread.join()


def preview_server(
    project_path: Path, port: int = 0, *, catalog_root: Path | None = None
) -> ThreadingHTTPServer:
    # Existing captured files are validated before being served.
    if catalog_root is None:
        builds = {}
        try:
            initial_directory, initial_manifest = latest_build(project_path)
            builds[(project_path.resolve(), initial_manifest["revision"])] = (
                initial_directory,
                initial_manifest,
            )
        except InputError:
            pass
        entries = []
        projects_by_name = {}
    else:
        entries = catalog_projects(catalog_root)
        projects_by_name = {item["name"]: item["path"] for item in entries}
        builds = {}
    watchers = {}
    watcher_lock = threading.Lock()

    def watch(path):
        with watcher_lock:
            if path not in watchers:
                watchers[path] = ProjectWatcher(
                    catalog_root or _runtime_root(path), path
                )
            return watchers[path]

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
                    states = {
                        name: watcher.status()
                        for name, path in projects_by_name.items()
                        if (watcher := watchers.get(path)) is not None
                    }
                    data = _catalog_html(entries, states)
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
            watcher = watch(selected_project)
            status_relative = "/".join(parts[2:]) if pinned else relative
            if status_relative == "status.json":
                expected = None
                if pinned:
                    try:
                        key = (selected_project, parts[1])
                        if key not in builds:
                            builds[key] = _build(selected_project, parts[1])
                        expected = builds[key][1]["input_identity"]
                    except InputError:
                        self.send_error(404)
                        return None
                data = json.dumps(watcher.status(expected)).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(data)
                return None
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
                if pinned:
                    self.send_error(404)
                else:
                    state = watcher.status()
                    refresh = (
                        '<meta http-equiv="refresh" content="2">'
                        if state["status"] == "updating"
                        else ""
                    )
                    data = (
                        "<!doctype html>"
                        + refresh
                        + "<title>Preview</title><p>"
                        + html.escape(state.get("error", "Preparing preview."))
                        + "</p><p>Correct inputs and refresh to retry.</p>"
                    ).encode()
                    self.send_response(503)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
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
                entry_path = (
                    f"/designs/{selected_name}/{relative}"
                    if selected_name is not None
                    else f"/{relative}"
                )
                base = (
                    f'<base href="{base_path}">'
                    f'<meta name="buratino-preview" content="{manifest["revision"]}" '
                    f'data-entry="{entry_path}">' + _REFRESH_SCRIPT
                ).encode()
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

    server = ThreadingHTTPServer(
        ("127.0.0.1", port), partial(Handler, directory=str(project_path))
    )
    if catalog_root is None:
        watch(project_path.resolve())
    original_close = server.server_close

    def close():
        for watcher in watchers.values():
            watcher.stop.set()
        original_close()
        for watcher in watchers.values():
            watcher.close()

    server.server_close = close
    return server


def preview_catalog_server(root: Path, port: int = 0) -> ThreadingHTTPServer:
    return preview_server(root / "projects", port, catalog_root=root)
