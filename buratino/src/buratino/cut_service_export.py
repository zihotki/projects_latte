"""Validate captured builds and publish cut-service exports safely."""

from __future__ import annotations

import json
import os
import shutil
import uuid
from pathlib import Path

from .cut_services import plan_export
from .environment import file_hash, read_json
from .preview import input_status, latest_build
from .project import InputError

_OWNER_FILE = ".buratino-cut-export.json"
_PROVIDERS = {"zagenzagen", "opmaatzagen"}


def _read_config(path: Path | None) -> dict | None:
    if path is None:
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read export config {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("Export config must be a JSON object.")
    return value


def _has_symlink_component(path: Path) -> bool:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if current.is_symlink():
            return True
    return False


def _safe_destination(project: Path, destination: Path, root: Path | None) -> Path:
    project = project.resolve()
    candidate = destination if destination.is_absolute() else Path.cwd() / destination
    candidate = candidate.absolute()
    if _has_symlink_component(candidate):
        raise ValueError("Export output path cannot contain a symbolic link.")
    resolved = candidate.resolve(strict=False)
    protected = [project / "build", project / "archive"]
    if root is not None:
        root = root.resolve()
        protected.extend(root / item for item in ("src", "vendor", "archive", "build"))
        projects = root / "projects"
        allowed_exports = project / "exports"
        if resolved == projects or (
            resolved.is_relative_to(projects)
            and not resolved.is_relative_to(allowed_exports)
        ):
            raise ValueError("Export output cannot replace project source directories.")
        if resolved == root:
            raise ValueError("Export output cannot replace the Buratino root.")
    allowed_exports = project / "exports"
    if resolved.is_relative_to(project) and not resolved.is_relative_to(
        allowed_exports
    ):
        raise ValueError(
            "Export output inside a project must be under its exports directory."
        )
    if resolved == allowed_exports:
        raise ValueError("Export output must be inside the project exports directory.")
    if resolved == project or any(
        resolved == item or resolved.is_relative_to(item) for item in protected
    ):
        raise ValueError(
            "Export output cannot replace the project, build, or archive tree."
        )
    if resolved == project / "project.py":
        raise ValueError("Export output cannot replace project source.")
    if resolved.exists() and not resolved.is_dir():
        raise ValueError("Export output must be a directory.")
    return resolved


def _owned_files(directory: Path) -> dict[str, str] | None:
    marker = directory / _OWNER_FILE
    if not marker.is_file() or marker.is_symlink():
        return None
    try:
        record = read_json(marker)
        files = record["files"]
        if not isinstance(files, dict) or not files:
            return None
        expected = set(files) | {_OWNER_FILE}
        entries = {item.name for item in directory.iterdir()}
        if entries != expected:
            return None
        for name, digest in files.items():
            if (
                not isinstance(name, str)
                or Path(name).name != name
                or name == _OWNER_FILE
                or not isinstance(digest, str)
            ):
                return None
            path = directory / name
            if path.is_symlink() or not path.is_file() or file_hash(path) != digest:
                return None
        return files
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _remove_owned(directory: Path, files: dict[str, str]) -> None:
    for name in files:
        (directory / name).unlink()
    (directory / _OWNER_FILE).unlink()
    directory.rmdir()


def _publish(destination: Path, files: dict[str, str]) -> None:
    parent = destination.parent
    parent.mkdir(parents=True, exist_ok=True)
    if _has_symlink_component(parent):
        raise ValueError("Export output path cannot contain a symbolic link.")
    stage = parent / f".buratino-cut-stage-{uuid.uuid4().hex}"
    backup = parent / f".buratino-cut-backup-{uuid.uuid4().hex}"
    stage.mkdir()
    try:
        hashes = {}
        for name, contents in files.items():
            if Path(name).name != name or (
                not name.endswith(".csv") and name != "index.json"
            ):
                raise ValueError(f"Unsafe provider output filename: {name!r}")
            payload = contents.encode("utf-8")
            (stage / name).write_bytes(payload)
            hashes[name] = file_hash(stage / name)
        if "index.json" not in files:
            raise ValueError("Cut-service export is missing index.json.")
        (stage / _OWNER_FILE).write_text(
            json.dumps({"schema": 1, "files": hashes}, indent=2) + "\n",
            encoding="utf-8",
        )

        old_files = _owned_files(destination) if destination.exists() else None
        if destination.exists() and old_files is None:
            if any(destination.iterdir()):
                raise ValueError(
                    "Refusing to replace non-empty unowned export directory: "
                    f"{destination}"
                )
            destination.rmdir()
        if destination.exists():
            destination.rename(backup)
        try:
            stage.rename(destination)
        except Exception:
            if backup.exists():
                backup.rename(destination)
            raise
        if old_files is not None:
            _remove_owned(backup, old_files)
    finally:
        if stage.exists():
            # This path was created by this invocation and contains only staged files.
            shutil.rmtree(stage)


def _summary_counts(summary: dict) -> tuple[int, int, int]:
    groups = summary.get("groups", [])
    issues = summary.get("issues", [])
    panels = sum(
        int(group.get("quantity", 0))
        for group in groups
        if isinstance(group, dict) and str(group.get("quantity", "0")).isdigit()
    )
    return len(groups), len(issues), panels


def export_cutlist(
    project_path: Path,
    provider: str,
    *,
    config_path: Path | None = None,
    output_path: Path | None = None,
) -> dict:
    if provider not in _PROVIDERS:
        raise ValueError(f"Unknown provider {provider!r}.")
    project = project_path.resolve()
    if not project.is_dir():
        raise InputError("input_unreadable", f"Project does not exist: {project}")
    try:
        build_dir, manifest = latest_build(project)
    except InputError as exc:
        raise InputError(exc.code, f"Run build first. {exc}") from exc
    state = input_status(project, manifest["input_identity"])
    if state.get("status") != "current":
        detail = state.get("error") or f"Project inputs are {state.get('status')}."
        raise InputError("build_stale", f"Run build first. {detail}")
    result = read_json(build_dir / "result.json")
    if result.get("input_identity") != manifest["input_identity"]:
        raise InputError(
            "build_unavailable",
            "Run build first. Result identity does not match manifest.",
        )
    if "report_part_codes" not in result:
        raise InputError(
            "build_unavailable",
            "Run build first. Captured report part codes are missing.",
        )
    result = {**result, "source_revision": manifest["revision"]}
    plan = plan_export(result, provider, _read_config(config_path))

    default = project / "exports" / manifest["revision"] / provider
    root = project.parent.parent if project.parent.name == "projects" else None
    destination = _safe_destination(project, output_path or default, root)
    csv_files = dict(plan.files)
    groups = plan.summary.get("groups", [])
    issues = plan.summary.get("issues", [])
    group_count, issue_count, panels = _summary_counts(plan.summary)
    reports = {
        name: Path(os.path.relpath(build_dir / filename, destination)).as_posix()
        for name, filename in (
            ("review", "report.html"),
            ("assembly", "report.html#assembly"),
        )
    }
    index = {
        "schema_version": 1,
        "provider": provider,
        "status": plan.status,
        "source_revision": manifest["revision"],
        "provider_product_selection_required": plan.summary.get(
            "provider_product_selection_required", True
        ),
        "source_input_identity": manifest["input_identity"],
        "reports": reports,
        "groups": groups,
        "file_context": {
            group["file"]: {
                key: group.get(key)
                for key in (
                    "material",
                    "panel_type",
                    "thickness_mm",
                    "provider_material",
                    "purchase_type",
                    "quantity",
                )
            }
            for group in groups
            if isinstance(group, dict) and isinstance(group.get("file"), str)
        },
        "issues": issues,
        "trace": plan.summary.get("trace", []),
        "row_count": plan.summary.get("row_count", 0),
        "files": list(csv_files),
    }
    serialized_index = json.dumps(index, indent=2, allow_nan=False) + "\n"
    _publish(destination, {**csv_files, "index.json": serialized_index})
    return {
        "status": plan.status,
        "provider": provider,
        "directory": str(destination),
        "files": sorted(csv_files) + ["index.json"],
        "group_count": group_count,
        "issue_count": issue_count,
        "physical_panels": panels,
        "row_count": plan.summary.get("row_count", 0),
        "groups": groups,
        "issues": issues,
        "source_revision": manifest["revision"],
        "provider_product_selection_required": plan.summary.get(
            "provider_product_selection_required", True
        ),
    }
