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
    """Check source and recorded import provenance without restricting edits."""
    lock = read_json(root / "cabineteer.lock.json")
    source = root / lock["source"]
    valid_commit = len(lock["commit"]) == 40 and all(
        c in "0123456789abcdef" for c in lock["commit"]
    )
    return {
        "ok": lock["source"] == "vendor/cabineteer"
        and (source / "pyproject.toml").is_file()
        and (source / "src/cabineteer/__init__.py").is_file()
        and bool(lock["repository"])
        and valid_commit
        and len(lock["patch_sha256"]) == 64,
        "commit": lock["commit"],
        "repository": lock["repository"],
        "source": str(source),
        "patch_sha256": lock["patch_sha256"],
    }


def engine_files(root: Path) -> dict[str, str]:
    """Hash the editable package, including data used by the engine."""
    source = root / "vendor/cabineteer/src/cabineteer"
    return {
        path.relative_to(root).as_posix(): file_hash(path)
        for path in sorted(source.rglob("*"))
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix not in {".pyc", ".pyo"}
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
    cache = root / ".cache"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "runtime.json").write_text(json.dumps(state, indent=2) + "\n")


def runtime_status(root: Path) -> dict:
    try:
        state = read_json(root / ".cache/runtime.json")
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
    expected = (root / "vendor/cabineteer/src/cabineteer/__init__.py").resolve()
    checks["installed_engine"] = {
        "ok": bool(spec and spec.origin) and Path(spec.origin).resolve() == expected,
        "origin": spec.origin if spec else None,
    }
    checks["cad"] = {"ok": importlib.util.find_spec("cadquery") is not None}
    assets = root / "vendor/three"
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
