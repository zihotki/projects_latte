#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

"$root_dir/scripts/python.sh" test
"$root_dir/buratino/bin/buratino" test-native
"$root_dir/buratino/bin/buratino" test
PNPM_CONFIG_VERIFY_DEPS_BEFORE_RUN=false \
  pnpm -C "$root_dir/cut_on_eight" run test:unit
