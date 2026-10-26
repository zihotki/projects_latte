"""Checks for the local source, installed engine, and viewing assets."""

import hashlib
import importlib.metadata
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path


def root_dir() -> Path:
    return Path(os.environ["BURATINO_ROOT"]).resolve()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_status(root: Path) -> dict:
    lock = read_json(root / "cabineteer.lock.json")
    checkout = root / lock["checkout"]

    def git(*args: str) -> str:
        return subprocess.check_output(
            ["git", "-C", str(checkout), *args], text=True, stderr=subprocess.PIPE
        ).strip()

    commit = git("rev-parse", "HEAD")
    dirty = bool(git("status", "--porcelain"))
    remote = git("remote", "get-url", "origin")
    detached = (
        subprocess.run(
            ["git", "-C", str(checkout), "symbolic-ref", "-q", "HEAD"],
            capture_output=True,
        ).returncode
        == 1
    )
    return {
        "ok": commit == lock["commit"]
        and remote == lock["repository"]
        and detached
        and not dirty,
        "commit": commit,
        "expected_commit": lock["commit"],
        "dirty": dirty,
        "detached": detached,
        "repository": remote,
    }


def _package_digest(directory: Path) -> dict[str, str]:
    return {
        str(path.relative_to(directory)): file_hash(path)
        for path in directory.rglob("*")
        if path.is_file() and path.suffix in {".py", ".json"}
    }


def runtime_identity() -> dict:
    return {
        "python": sys.version.split()[0],
        "packages": {
            distribution.metadata["Name"]
            .lower()
            .replace("_", "-"): distribution.version
            for distribution in importlib.metadata.distributions()
        },
    }


def capture_runtime(root: Path) -> None:
    state = {"lock_sha256": file_hash(root / "uv.lock"), **runtime_identity()}
    (root / ".local/runtime.json").write_text(json.dumps(state, indent=2) + "\n")


def runtime_status(root: Path) -> dict:
    try:
        state = read_json(root / ".local/runtime.json")
        actual = runtime_identity()
        return {
            "ok": state["lock_sha256"] == file_hash(root / "uv.lock")
            and state["python"] == actual["python"]
            and state["packages"] == actual["packages"],
            "python": actual["python"],
        }
    except (OSError, ValueError, KeyError) as exc:
        return {"ok": False, "error": str(exc)}


def doctor(root: Path) -> dict:
    checks = {}
    checks["runtime"] = runtime_status(root)
    try:
        checks["source"] = source_status(root)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        checks["source"] = {"ok": False, "error": str(exc)}
    spec = importlib.util.find_spec("cabineteer")
    checkout = root / read_json(root / "cabineteer.lock.json")["checkout"]
    checks["installed_engine"] = {
        "ok": bool(spec and spec.origin)
        and _package_digest(checkout / "src/cabineteer")
        == _package_digest(Path(spec.origin).parent),
    }
    checks["cad"] = {"ok": importlib.util.find_spec("cadquery") is not None}
    assets = root / ".local/viewer/three"
    try:
        index = read_json(assets / "files.json")
        lock = read_json(root / "viewer-assets.lock.json")
        checks["viewer"] = {
            "ok": index["integrity"] == lock["integrity"]
            and bool(index["files"])
            and all(
                (assets / path).is_file() and file_hash(assets / path) == digest
                for path, digest in index["files"].items()
            ),
            "version": lock["version"],
        }
    except (OSError, ValueError, KeyError) as exc:
        checks["viewer"] = {"ok": False, "error": str(exc)}
    return {"ok": all(item["ok"] for item in checks.values()), "checks": checks}
