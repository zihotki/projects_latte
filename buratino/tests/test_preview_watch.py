"""Fast preview tests use tiny published drafts instead of CAD builds."""

import json
import os
import signal
import subprocess
import threading
import time
import urllib.request
from contextlib import suppress

import pytest

from buratino import preview
from buratino.environment import file_hash
from buratino.project import InputError


def wait_for(predicate, timeout=4):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("Preview did not reach the expected state")


def publish(project, identity, number):
    revision = f"{number:012x}-{number:08x}"
    directory = project / "build" / revision
    directory.mkdir(parents=True)
    page = directory / "preview.html"
    page.write_text(f"<html><body>{identity}</body></html>")
    manifest = {
        "revision": revision,
        "status": "draft",
        "input_identity": identity,
        "files": {"preview.html": file_hash(page)},
    }
    (directory / "manifest.json").write_text(json.dumps(manifest))
    (project / "build/latest.json").write_text(json.dumps({"revision": revision}))
    return manifest


def setup_project(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    (project / "project.py").write_text("a")
    monkeypatch.setattr(
        preview, "input_identity", lambda path: (path / "project.py").read_text()
    )
    publish(project, "a", 1)
    return project


def test_debounce_invalid_retention_and_recovery(tmp_path, monkeypatch):
    project = setup_project(tmp_path, monkeypatch)
    calls = []

    def build(watcher):
        identity = preview.input_identity(project)
        calls.append(identity)
        if identity == "invalid":
            raise InputError("invalid_source", "Incomplete edit")
        publish(project, identity, len(calls) + 1)

    monkeypatch.setattr(preview.ProjectWatcher, "_build", build)
    watcher = preview.ProjectWatcher(tmp_path, project, poll=0.01, debounce=0.08)
    try:
        wait_for(lambda: watcher.identity == "a")
        (project / "project.py").write_text("b")
        time.sleep(0.03)
        (project / "project.py").write_text("c")
        wait_for(lambda: watcher.status()["revision"] == "000000000002-00000002")
        assert calls == ["c"]
        (project / "project.py").write_text("invalid")
        wait_for(lambda: watcher.status()["status"] == "invalid")
        assert watcher.status()["error"] == "Incomplete edit"
        assert preview.latest_build(project)[1]["input_identity"] == "c"
        time.sleep(0.15)
        assert calls == ["c", "invalid"]
        (project / "project.py").unlink()
        wait_for(lambda: watcher.status()["status"] == "unavailable")
        (project / "project.py").write_text("fixed")
        wait_for(lambda: watcher.status()["status"] == "current")
        assert calls == ["c", "invalid", "fixed"]
        assert preview.latest_build(project)[1]["input_identity"] == "fixed"
    finally:
        watcher.close()
    assert not watcher.thread.is_alive()


def test_changes_during_build_are_coalesced_and_serialized(tmp_path, monkeypatch):
    project = setup_project(tmp_path, monkeypatch)
    started, release = threading.Event(), threading.Event()
    calls = []

    def build(watcher):
        identity = preview.input_identity(project)
        calls.append(identity)
        if identity == "b":
            started.set()
            assert release.wait(3)
            raise InputError("inputs_changed", "Inputs changed during build")
        publish(project, identity, 2)

    monkeypatch.setattr(preview.ProjectWatcher, "_build", build)
    watcher = preview.ProjectWatcher(tmp_path, project, poll=0.01, debounce=0.03)
    try:
        (project / "project.py").write_text("b")
        assert started.wait(3)
        (project / "project.py").write_text("c")
        (project / "project.py").write_text("d")
        assert watcher.status()["status"] == "updating"
        assert preview.latest_build(project)[1]["input_identity"] == "a"
        release.set()
        wait_for(lambda: watcher.status()["status"] == "current")
        assert calls == ["b", "d"]
    finally:
        release.set()
        watcher.close()


def test_busy_build_retries_when_lock_clears(tmp_path, monkeypatch):
    project = setup_project(tmp_path, monkeypatch)
    lock = project / "build/.lock"
    lock.write_text("other-owner")
    calls = []

    def build(watcher):
        calls.append(True)
        if lock.exists():
            raise InputError("build_busy", "Another build owns the lock")
        publish(project, "b", 2)

    monkeypatch.setattr(preview.ProjectWatcher, "_build", build)
    watcher = preview.ProjectWatcher(tmp_path, project, poll=0.01, debounce=0.02)
    try:
        (project / "project.py").write_text("b")
        wait_for(lambda: watcher.status()["status"] == "stale")
        lock.unlink()
        wait_for(lambda: watcher.status()["status"] == "current")
        assert len(calls) == 2
    finally:
        watcher.close()


def test_build_runs_in_fresh_interpreter_for_changed_engine(tmp_path, monkeypatch):
    # A tiny replacement engine proves that imports are fresh for each actual build.
    package = tmp_path / "buratino"
    package.mkdir()
    (package / "__init__.py").write_text("")
    source = package / "build.py"
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    monkeypatch.chdir(tmp_path)
    watcher = preview.ProjectWatcher.__new__(preview.ProjectWatcher)
    watcher.root = watcher.project = tmp_path
    watcher.stop, watcher.poll = threading.Event(), 0.01
    watcher.identity = "observed"
    for value in ("first", "changed engine"):
        source.write_text(
            "def build_project(root, project, *, expected_identity=None):\n"
            f"    (project / 'output').write_text({value!r})\n"
            "    (project / 'expected').write_text(expected_identity)\n"
        )
        watcher._build()
        assert (tmp_path / "output").read_text() == value
        assert (tmp_path / "expected").read_text() == "observed"


@pytest.mark.parametrize("catalog", [False, True])
def test_http_keeps_last_good_responsive_during_rebuild(tmp_path, monkeypatch, catalog):
    project = setup_project(tmp_path, monkeypatch)
    if catalog:
        (tmp_path / "projects").mkdir()
        project = project.rename(tmp_path / "projects/project")
    prefix = "/designs/project" if catalog else ""
    started, release = threading.Event(), threading.Event()

    def build(watcher):
        started.set()
        assert release.wait(3)
        publish(project, preview.input_identity(project), 2)

    monkeypatch.setattr(preview.ProjectWatcher, "_build", build)
    server = (
        preview.preview_catalog_server(tmp_path)
        if catalog
        else preview.preview_server(project)
    )
    with server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"

        def get(path):
            with urllib.request.urlopen(base + prefix + path, timeout=1) as response:
                return response.read()

        try:
            first = get("/preview.html")
            assert f'data-entry="{prefix}/preview.html"'.encode() in first
            assert b"window.buratinoPreviewRefresh = true" in first
            (project / "project.py").write_text("b")
            assert started.wait(3)
            assert get("/preview.html") == first
            status = json.loads(get("/revisions/000000000001-00000001/status.json"))
            assert status == {"status": "updating", "revision": "000000000001-00000001"}
            release.set()
            wait_for(lambda: json.loads(get("/status.json"))["revision"].endswith("2"))
            assert b'content="000000000002-00000002"' in get("/preview.html")
            assert (
                get("/revisions/000000000001-00000001/preview.html")
                == (project / "build/000000000001-00000001/preview.html").read_bytes()
            )
        finally:
            release.set()
            server.shutdown()
            thread.join()


def test_shutdown_stops_child_and_cleans_only_its_lock(tmp_path, monkeypatch):
    package = tmp_path / "buratino"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "build.py").write_text(
        "import os, time, subprocess, sys\n"
        "def build_project(root, project, *, expected_identity=None):\n"
        '    descendant = ("import os, signal, time; from pathlib import Path; "\n'
        '        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "\n'
        "        + f\"Path({str(project / 'descendant')!r})\"\n"
        '        + ".write_text(str(os.getpid())); "\n'
        '        + "time.sleep(30)")\n'
        "    subprocess.Popen([sys.executable, '-c', descendant])\n"
        "    (project / 'build').mkdir()\n"
        "    (project / 'build/.lock').write_text(str(os.getpid()))\n"
        "    time.sleep(30)\n"
    )
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    watcher = preview.ProjectWatcher.__new__(preview.ProjectWatcher)
    watcher.root = watcher.project = tmp_path
    watcher.stop, watcher.poll = threading.Event(), 0.01
    watcher.identity = "observed"
    errors = []

    def run():
        try:
            watcher._build()
        except InputError as exc:
            errors.append(exc.code)

    thread = threading.Thread(target=run)
    thread.start()
    try:
        wait_for(lambda: (tmp_path / "build/.lock").exists())
        wait_for(lambda: (tmp_path / "descendant").exists())
    finally:
        watcher.stop.set()
        thread.join(timeout=6)
    descendant = int((tmp_path / "descendant").read_text())

    def descendant_stopped():
        result = subprocess.run(
            ["ps", "-o", "stat=", "-p", str(descendant)],
            capture_output=True,
            text=True,
            check=False,
        )
        return not result.stdout.strip() or result.stdout.strip().startswith("Z")

    try:
        assert not thread.is_alive()
        assert errors == ["build_stopped"]
        assert not (tmp_path / "build/.lock").exists()
        wait_for(descendant_stopped)
    finally:
        with suppress(ProcessLookupError):
            os.kill(descendant, signal.SIGKILL)


def test_build_rejects_capture_changed_after_engine_import(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from buratino import build

    project = setup_project(tmp_path, monkeypatch)
    monkeypatch.setattr(build, "doctor", lambda _root: {"ok": True})
    # Simulate imported code for the observed identity, then a later input capture.
    monkeypatch.setattr(
        build, "load_project", lambda _path: SimpleNamespace(identity="new-rule-hash")
    )

    def unexpected_calculation(_project):
        raise AssertionError("Changed captures must stop before calculation")

    monkeypatch.setattr(build, "calculate", unexpected_calculation)
    with pytest.raises(InputError) as error:
        build.build_project(tmp_path, project, expected_identity="imported-rule-hash")
    assert error.value.code == "inputs_changed"
    assert preview.latest_build(project)[1]["input_identity"] == "a"
