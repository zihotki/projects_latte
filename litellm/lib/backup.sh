#!/usr/bin/env bash

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  printf 'Source this file from the LiteLLM command.\n' >&2
  exit 2
fi

# pgBackRest info contains only successful backups. The newest full backup
# starts the current chain, even when newer incremental backups exist.
backup_summary() {
  local now="${1:-$(date +%s)}"
  python3 -c '
import datetime
import json
import sys

try:
    stanzas = json.load(sys.stdin)
    backups = next((s.get("backup", []) for s in stanzas if s.get("name") == "litellm"), [])
    backups = [b for b in backups if b.get("timestamp", {}).get("stop") and b.get("type") in ("full", "incr", "diff")]
    newest = max(backups, key=lambda b: b["timestamp"]["stop"], default=None)
    full = max((b for b in backups if b["type"] == "full"), key=lambda b: b["timestamp"]["stop"], default=None)
    now = int(sys.argv[1])
    selected = "full" if full is None or now - int(full["timestamp"]["stop"]) >= 7 * 24 * 60 * 60 else "incr"
    if newest is None:
        print("none|none|full")
    else:
        stamp = datetime.datetime.fromtimestamp(int(newest["timestamp"]["stop"]), datetime.timezone.utc).isoformat()
        print("{}|{}|{}".format(newest["type"], stamp, selected))
except (ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
    print("Invalid pgBackRest metadata: {}".format(error), file=sys.stderr)
    sys.exit(1)
' "$now"
}

backup_info() {
  docker compose -f "$LITELLM_COMPOSE_FILE" exec -T --user postgres postgres \
    pgbackrest --stanza=litellm info --output=json
}

backup_run() {
  local summary backup_type
  summary="$(backup_info | backup_summary)" || return 1
  IFS='|' read -r backup_type backup_time backup_choice <<< "$summary"
  printf 'Last successful backup: %s %s\n' "$backup_type" "$backup_time"
  printf 'Starting %s backup.\n' "$backup_choice"
  docker compose -f "$LITELLM_COMPOSE_FILE" exec -T --user postgres postgres \
    pgbackrest --stanza=litellm --type="$backup_choice" backup
}
