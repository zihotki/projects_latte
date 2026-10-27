"""Explicit commands for the first cabinet slice."""

import argparse
import json
import sys
from pathlib import Path

from .build import build_project
from .environment import doctor, root_dir
from .preview import preview_server
from .project import InputError


def project_path(root: Path, value: str) -> Path:
    candidate = (root / value).resolve()
    if not candidate.is_relative_to(root / "projects"):
        raise InputError(
            "invalid_project_path", "Project must be inside buratino/projects."
        )
    return candidate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Buratino cabinet draft tools")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Check local engine and viewing assets")
    build = commands.add_parser("build", help="Calculate and generate a cabinet draft")
    build.add_argument("project", help="Project path relative to buratino/")
    build.add_argument(
        "--json", action="store_true", help="Print the full build result as JSON"
    )
    preview = commands.add_parser("preview", help="Serve the last draft on loopback")
    preview.add_argument("project", help="Project path relative to buratino/")
    preview.add_argument("--port", type=int, default=0)
    args = parser.parse_args(argv)
    root = root_dir()
    try:
        if args.command == "doctor":
            result = doctor(root)
            print(json.dumps(result, indent=2))
            return 0 if result["ok"] else 1
        path = project_path(root, args.project)
        if args.command == "build":
            result = build_project(root, path)
            if args.json:
                print(json.dumps(result, indent=2))
            else:
                print(f"Draft built: {result['directory']}")
                print("Not ready for manufacturing. See report.html for checks.")
            return 0
        with preview_server(path, args.port) as server:
            print(
                json.dumps(
                    {
                        "status": "draft",
                        "manufacturing_ready": False,
                        "url": f"http://127.0.0.1:{server.server_port}/preview.html",
                        "message": (
                            "Press Ctrl-C to stop. "
                            "Rebuild explicitly after input changes."
                        ),
                    }
                ),
                flush=True,
            )
            server.serve_forever()
        return 0
    except KeyboardInterrupt:
        return 0
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "code": getattr(exc, "code", "operation_failed"),
                    "message": str(exc),
                    "affected": getattr(exc, "affected", ""),
                }
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
