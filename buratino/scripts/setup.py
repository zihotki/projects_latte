"""Explicit installation into Buratino's local directory."""

import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from buratino.environment import file_hash, read_json, source_status  # noqa: E402


def install_assets() -> None:
    lock = read_json(ROOT / "viewer-assets.lock.json")
    asset_root = ROOT / ".local/viewer"
    asset_root.mkdir(parents=True, exist_ok=True)
    archive = asset_root / f"three-{lock['version']}.tgz"
    if not archive.exists():
        print(f"Downloading Three.js {lock['version']}", flush=True)
        with urllib.request.urlopen(lock["url"], timeout=60) as response:
            data = response.read(50 * 1024 * 1024 + 1)
        if len(data) > 50 * 1024 * 1024:
            raise ValueError("Viewer archive exceeds the download limit.")
        archive.write_bytes(data)
    digest = base64.b64encode(hashlib.sha512(archive.read_bytes()).digest()).decode()
    if f"sha512-{digest}" != lock["integrity"]:
        raise ValueError(f"Viewer integrity mismatch. Remove {archive} and retry.")
    with tempfile.TemporaryDirectory(dir=asset_root) as temporary:
        stage = Path(temporary) / "three"
        stage.mkdir()
        with tarfile.open(archive, "r:gz") as package:
            for member in package.getmembers():
                relative = Path(member.name).relative_to("package")
                allowed = (
                    str(relative) == "LICENSE"
                    or str(relative) == "build/three.module.js"
                    or (
                        str(relative).startswith("examples/jsm/")
                        and relative.suffix == ".js"
                    )
                )
                if not allowed or not member.isfile():
                    continue
                target = (stage / relative).resolve()
                if not target.is_relative_to(stage.resolve()):
                    raise ValueError("Unsafe viewer archive path.")
                target.parent.mkdir(parents=True, exist_ok=True)
                with package.extractfile(member) as source:
                    target.write_bytes(source.read())
        index = {
            "integrity": lock["integrity"],
            "files": {
                str(path.relative_to(stage)): file_hash(path)
                for path in stage.rglob("*")
                if path.is_file()
            },
        }
        (stage / "files.json").write_text(json.dumps(index, indent=2) + "\n")
        target = asset_root / "three"
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(stage, target)


def main() -> None:
    if not source_status(ROOT)["ok"]:
        raise ValueError("Cabineteer source or provenance is missing or invalid.")
    if not shutil.which("uv"):
        raise ValueError("Install UV before running Buratino setup.")
    subprocess.run(
        ["uv", "sync", "--project", str(ROOT), "--frozen", "--python", "3.12"],
        check=True,
        env=os.environ,
    )
    subprocess.run(
        [
            str(ROOT / ".local/venv/bin/python"),
            "-c",
            "from pathlib import Path; "
            "from buratino.environment import capture_runtime; "
            "import sys; capture_runtime(Path(sys.argv[1]))",
            str(ROOT),
        ],
        check=True,
    )
    install_assets()
    print("Setup complete. Next: ./buratino/bin/buratino doctor")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"Setup failed: {exc}", file=sys.stderr)
        sys.exit(1)
