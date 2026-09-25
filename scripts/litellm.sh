#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
command="${1:-help}"

help() {
  cat <<'EOF'
Usage: ./scripts/litellm.sh COMMAND [OPTIONS]

Commands:
  start          Back up PostgreSQL, then start the gateway.
  status         Show service state and the latest backup.
  backup         Back up the running database now.
  restore-check  Test the latest backup in a separate volume.
  stop           Stop the gateway and keep its data.
  help           Show this help.

Options:
  start --reinitialize-backup-repo  Start a new backup chain when the old one is lost.
  restore-check --expect-key-alias ALIAS  Check a backed-up virtual key.

First setup: see litellm/README.md for Keychain items and Docker Desktop.
Suggested first command: ./scripts/litellm.sh start
EOF
}

case "$command" in
  help|-h|--help)
    help
    ;;
  start|status|backup|restore-check|stop)
    "$root_dir/litellm/bin/litellm" "$@"
    case "$command" in
      start) printf '\nNext: ./scripts/litellm.sh status\n' ;;
      status) printf '\nIf stopped: ./scripts/litellm.sh start\nIf running: ./scripts/litellm.sh backup\n' ;;
      backup) printf '\nNext: ./scripts/litellm.sh restore-check\nThen: ./scripts/litellm.sh stop\n' ;;
      restore-check) printf '\nNext: ./scripts/litellm.sh status\n' ;;
      stop) printf '\nNext session: ./scripts/litellm.sh start\n' ;;
    esac
    ;;
  *)
    help >&2
    exit 2
    ;;
esac
