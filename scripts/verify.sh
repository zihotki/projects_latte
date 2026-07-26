#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

"$root_dir/scripts/check.sh"
"$root_dir/scripts/test.sh"
"$root_dir/scripts/integration.sh"
