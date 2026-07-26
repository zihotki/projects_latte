#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

"$root_dir/scripts/python.sh" check
PNPM_CONFIG_VERIFY_DEPS_BEFORE_RUN=false \
  pnpm -C "$root_dir/cut_on_eight" run ci:check
