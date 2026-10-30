"""Load one authored project module and identify all rules used to build it."""

from __future__ import annotations

import hashlib
import json
import math
import multiprocessing
import os
from dataclasses import asdict, dataclass, is_dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from .environment import file_hash
from .project_worker import execute_project

if TYPE_CHECKING:
    from cabineteer.drawer import DrawerConfig
    from cabineteer.project import CabinetProject


class InputError(ValueError):
    """An actionable input error with a stable code and location."""

    def __init__(self, code: str, message: str, affected: str = ""):
        super().__init__(message)
        self.code = code
        self.affected = affected


@dataclass(frozen=True)
class ProjectInputs:
    path: Path
    variables: dict
    calculated: dict
    native_project: CabinetProject
    drawer_configs: dict[str, DrawerConfig]
    source: str
    source_hash: str
    rule_files: dict[str, str]
    identity: str


def _runtime_root(path: Path) -> Path:
    configured = os.environ.get("BURATINO_ROOT")
    if configured:
        return Path(configured).resolve()
    for parent in (path, *path.parents):
        if (parent / "cabineteer.lock.json").is_file():
            return parent
    # Installed package location, including temporary project fixtures.
    return Path(__file__).resolve().parents[2]


def _identity_files(root: Path) -> dict[str, str]:
    """Hash local build rules without importing or executing authored code."""
    files: dict[str, str] = {}
    for relative in (
        "cabineteer.lock.json",
        "uv.lock",
        "viewer-assets.lock.json",
        ".cache/runtime.json",
    ):
        candidate = root / relative
        if candidate.is_file():
            files[relative] = file_hash(candidate)
    from .environment import engine_files

    files.update(engine_files(root))
    adapter = root / "src/buratino"
    if adapter.is_dir():
        for candidate in sorted(adapter.rglob("*.py")):
            if "__pycache__" not in candidate.parts:
                files[candidate.relative_to(root).as_posix()] = file_hash(candidate)
        for candidate in sorted(adapter.rglob("*")):
            if candidate.is_file() and candidate.suffix in {
                ".js",
                ".css",
                ".json",
                ".toml",
                ".yaml",
                ".yml",
            }:
                files[candidate.relative_to(root).as_posix()] = file_hash(candidate)
    # Profiles may be data files outside the Python package.
    for directory in (root / "profiles", root / "catalog"):
        if directory.is_dir():
            for candidate in sorted(directory.rglob("*")):
                if candidate.is_file() and candidate.suffix in {
                    ".json",
                    ".toml",
                    ".yaml",
                    ".yml",
                }:
                    files[candidate.relative_to(root).as_posix()] = file_hash(candidate)
    return files


def input_identity(
    path: Path,
    *,
    source: bytes | None = None,
    rules: dict[str, str] | None = None,
) -> str:
    """Return current source/rule identity without executing the project."""
    path = path.resolve()
    source_path = path / "project.py"
    try:
        captured = source if source is not None else source_path.read_bytes()
        root = _runtime_root(path)
        captured_rules = rules if rules is not None else _identity_files(root)
    except OSError as exc:
        raise InputError("input_unreadable", str(exc), str(source_path)) from exc
    value = {
        "source_sha256": hashlib.sha256(captured).hexdigest(),
        "rules": captured_rules,
    }
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _finite_map(value: object, location: str) -> dict:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise InputError(
            "invalid_export", f"{location} must be a string-keyed map.", location
        )
    try:
        encoded = json.dumps(value, allow_nan=False)
        decoded = json.loads(encoded)
    except (TypeError, ValueError) as exc:
        raise InputError(
            "invalid_export",
            f"{location} must contain finite JSON values: {exc}",
            location,
        ) from exc

    def check(item: object) -> bool:
        if isinstance(item, float):
            return math.isfinite(item)
        if isinstance(item, list):
            return all(check(child) for child in item)
        if isinstance(item, dict):
            return all(
                isinstance(key, str) and check(child) for key, child in item.items()
            )
        return item is None or isinstance(item, str | int | bool)

    if not check(decoded):
        raise InputError(
            "invalid_export", f"{location} must contain finite JSON values.", location
        )
    return decoded


def load_project(path: Path) -> ProjectInputs:
    """Execute the captured project source once in a fresh spawned process."""
    path = path.resolve()
    source_path = path / "project.py"
    try:
        source_bytes = source_path.read_bytes()
        source = source_bytes.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise InputError("input_unreadable", str(exc), str(source_path)) from exc
    try:
        rules = _identity_files(_runtime_root(path))
    except OSError as exc:
        raise InputError("input_unreadable", str(exc), str(path)) from exc

    context = multiprocessing.get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    process = context.Process(
        target=execute_project,
        args=(send, source, str(source_path)),
    )
    process.start()
    send.close()
    try:
        result = receive.recv()
    except EOFError as exc:
        process.join()
        raise InputError(
            "project_execution_failed",
            f"Project worker exited with status {process.exitcode}.",
            str(source_path),
        ) from exc
    finally:
        receive.close()
    process.join()
    if process.exitcode != 0:
        raise InputError(
            "project_execution_failed",
            f"Project worker exited with status {process.exitcode}.",
            str(source_path),
        )
    if not result["ok"]:
        raise InputError(result["code"], result["message"], str(source_path))

    values = result["exports"]
    missing = {"variables", "calculated", "project"} - set(values)
    if missing:
        raise InputError(
            "missing_export",
            f"Missing required exports: {', '.join(sorted(missing))}.",
            str(source_path),
        )
    variables = _finite_map(values["variables"], "variables")
    calculated = _finite_map(values["calculated"], "calculated")

    try:
        from cabineteer.drawer import DrawerConfig
        from cabineteer.project import CabinetProject
    except ImportError as exc:
        raise InputError("native_api_unavailable", str(exc)) from exc
    native_project = values["project"]
    if not isinstance(native_project, CabinetProject):
        raise InputError(
            "invalid_project", "project must be a native CabinetProject.", "project"
        )
    drawer_configs = values.get("drawer_configs", {})
    if not isinstance(drawer_configs, dict) or any(
        not isinstance(key, str) or not key or not isinstance(config, DrawerConfig)
        for key, config in drawer_configs.items()
    ):
        raise InputError(
            "invalid_drawer_configs",
            "drawer_configs must map named paths to native DrawerConfig objects.",
            "drawer_configs",
        )

    source_hash = hashlib.sha256(source_bytes).hexdigest()
    return ProjectInputs(
        path=path,
        variables=variables,
        calculated=calculated,
        native_project=native_project,
        drawer_configs=drawer_configs,
        source=source,
        source_hash=source_hash,
        rule_files=rules,
        identity=input_identity(path, source=source_bytes, rules=rules),
    )


def native_snapshot(
    project: ProjectInputs, built_drawer_configs: dict[str, DrawerConfig] | None = None
) -> dict:
    """Return JSON-ready records of native configs resolved from this source."""
    from cabineteer.profiles import lower_slide_keys
    from cabineteer.project import project_to_dict

    from .drawers import EB20_SLIDE_KEYS, eb20_profile_for_key, register_eb20_profile

    def plain(value):
        if isinstance(value, Enum):
            return value.value
        if is_dataclass(value):
            fields = asdict(value)
            fields.update(
                {key: item for key, item in vars(value).items() if key not in fields}
            )
            return plain(fields)
        if isinstance(value, dict):
            return {str(key): plain(item) for key, item in value.items()}
        if isinstance(value, list | tuple):
            return [plain(item) for item in value]
        return value

    native_project = project.native_project
    is_space_project = (
        native_project.space_model is not None
        or native_project.space_cabinets
        or native_project.space_modules
    )
    if is_space_project:
        from cabineteer.hardware import get_slide
        from cabineteer.project import project_to_dict

        is_space_assembly = native_project.layout is not None
        plan = (
            native_project.resolved_space_assembly()
            if is_space_assembly
            else native_project.resolved_space_model()
        )
        selected = sorted(
            {item["slide_key"] for item in plan.contents if item.get("slide_key")}
        )
        hinge_keys = sorted(
            {item["hinge_key"] for item in plan.fronts if item.get("hinge_key")}
        )
        resolved = plain(plan.to_dict())
        return {
            "project": plain(project_to_dict(native_project)),
            "resolved_space_plan": resolved,
            **({"resolved_space_assembly": resolved} if is_space_assembly else {}),
            **({"resolved_space_model": resolved} if not is_space_assembly else {}),
            "drawer_configs": {},
            "built_drawer_configs": {},
            "hardware_profiles": {
                key: {"native_slide_spec": plain(get_slide(key))} for key in selected
            },
            "selected_hinge_keys": hinge_keys,
            "cabinet_hardware_profiles": {
                project.native_project.name: {
                    "slide_key": selected[0],
                    "slide_keys": selected,
                }
            }
            if selected
            else {},
        }

    configs = (
        built_drawer_configs
        if built_drawer_configs is not None
        else project.drawer_configs
    )
    keys = {cfg.slide_key for cfg in configs.values()}
    spec = project.native_project.profile_assembly
    selected_by_cabinet = {}
    if spec is not None:
        recipes = {item.cabinet: item for item in spec.lower_drawers}
        selected_by_cabinet = {
            name: tuple(sorted(set(lower_slide_keys(cabinet, recipes[name]))))
            for name, cabinet in project.native_project.resolved()
            if name in recipes
        }
        if not recipes and spec.faces and spec.faces.drawer:
            selected_by_cabinet[spec.lower] = (spec.faces.drawer["slide_key"],)
        keys.update(
            key for selected in selected_by_cabinet.values() for key in selected
        )
        keys.update(item.slide_key for item in spec.upper_drawers)
    # Retain the historical default snapshot entry for projects with no drawers.
    if not keys:
        keys = {EB20_SLIDE_KEYS[project.variables.get("runner_length_mm", 450)]}
    profiles = {
        key: {
            "source_data": plain(eb20_profile_for_key(key)),
            "native_slide_spec": plain(
                register_eb20_profile(eb20_profile_for_key(key)["runner_length_mm"])
            ),
        }
        for key in sorted(keys)
    }
    if len(profiles) == 1:
        profiles["hettich_quadro_v6_eb20"] = next(iter(profiles.values()))

    cabinet_profiles = {}
    for name, _ in project.native_project.resolved():
        prefix = f"{name}.drawer." if built_drawer_configs is not None else f"{name}/"
        matching = [cfg for key, cfg in configs.items() if key.startswith(prefix)]
        selected = selected_by_cabinet.get(name) or tuple(
            sorted({cfg.slide_key for cfg in matching})
        )
        if selected:
            cabinet_profiles[name] = (
                {
                    "slide_key": selected[0],
                    "source_data": plain(eb20_profile_for_key(selected[0])),
                }
                if len(selected) == 1
                else {
                    "slide_key": None,
                    "slide_keys": list(selected),
                    "source_data_by_key": {
                        key: plain(eb20_profile_for_key(key)) for key in selected
                    },
                }
            )

    return {
        "project": plain(project_to_dict(project.native_project)),
        "resolved_cabinets": [
            {"name": name, "config": plain(config)}
            for name, config in project.native_project.resolved()
        ],
        "drawer_configs": plain(project.drawer_configs),
        "built_drawer_configs": plain(built_drawer_configs or {}),
        "hardware_profiles": profiles,
        "cabinet_hardware_profiles": cabinet_profiles,
    }
