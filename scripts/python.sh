#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root_dir"

export UV_CACHE_DIR="$root_dir/.local/uv-cache"
export UV_PYTHON_INSTALL_DIR="$root_dir/.local/uv-python"

case "${1:-}" in
  check)
    uv run --frozen --group dev ruff check .
    uv run --frozen --group dev ruff format --check .
    uv run --frozen --group dev pyright
    ;;
  test)
    if find python -type f \( -name 'test_*.py' -o -name '*_test.py' \) -print -quit 2>/dev/null | grep -q .; then
      uv run --frozen --group dev pytest
    else
      echo 'No Python tests discovered; skipping pytest.'
    fi
    ;;
  *)
    echo "Usage: $0 {check|test}" >&2
    exit 64
    ;;
esac
