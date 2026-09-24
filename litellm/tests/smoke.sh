#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
root_dir="$(cd "$project_dir/.." && pwd)"
command="$project_dir/bin/litellm"
test_dir="$root_dir/.local/litellm-smoke-$$"
mkdir -p "$test_dir/bin" "$test_dir/backups" "$test_dir/other-backups" "$test_dir/public" "$test_dir/unwritable"
chmod 700 "$test_dir/backups"
chmod 700 "$test_dir/other-backups"
chmod 755 "$test_dir/public"
chmod 500 "$test_dir/unwritable"
export LITELLM_BACKUP_DIR="$test_dir/backups"
export COMPOSE_PROJECT_NAME="litellmsmoke$$"
export DOCKER_REAL="$(command -v docker)"
export PATH="$test_dir/bin:$PATH"

cat > "$test_dir/bin/security" <<'MOCK'
#!/usr/bin/env bash
if [[ "${LITELLM_SMOKE_KEYCHAIN:-}" == missing ]]; then exit 44; fi
case "$*" in
  *projectslatte.litellm.master*) printf 'sk-local-smoke-master-1234567890\n' ;;
  *projectslatte.litellm.salt*) printf 'local-smoke-salt-1234567890\n' ;;
  *projectslatte.litellm.postgres*) printf 'local-smoke-postgres-password\n' ;;
  *projectslatte.litellm.openrouter*) printf 'sk-local-smoke-openrouter\n' ;;
  *) exit 44 ;;
esac
MOCK
chmod +x "$test_dir/bin/security"

cat > "$test_dir/bin/docker" <<'MOCK'
#!/usr/bin/env bash
if [[ "${LITELLM_SMOKE_FAIL_BACKUP:-}" == yes && "$*" == *'--type=incr backup'* ]]; then
  printf 'Injected backup failure.\n' >&2
  exit 45
fi
exec "$DOCKER_REAL" "$@"
MOCK
chmod +x "$test_dir/bin/docker"

compose() { "$DOCKER_REAL" compose -f "$project_dir/compose.yaml" "$@"; }
count_backups() {
  "$DOCKER_REAL" run --rm --volume "$LITELLM_BACKUP_DIR:/var/lib/pgbackrest:ro" \
    --entrypoint pgbackrest projectslatte/litellm-postgres:18.6-trixie-pgbackrest-2.55.1 \
    --stanza=litellm info --output=json \
    | python3 -c 'import json,sys; print(len(json.load(sys.stdin)[0]["backup"]))'
}
assert_stopped() {
  [[ -z "$(compose ps --status running -q proxy)" ]]
  [[ -z "$(compose ps --status running -q postgres)" ]]
}
cleanup() {
  local result=$?
  if (( result != 0 )); then
    for log in "$test_dir"/{first,second,third,mismatched-backup,mismatched-status,manual}.log; do
      if [[ -f "$log" ]]; then
        printf '%s:\n' "$(basename "$log")" >&2
        tail -n 10 "$log" >&2
      fi
    done
  fi
  unset LITELLM_SMOKE_FAIL_BACKUP
  compose down --volumes --remove-orphans >/dev/null 2>&1 || true
  rm -rf "$test_dir"
}
trap cleanup EXIT

compose build postgres >/dev/null
"$command" status > "$test_dir/empty-status.log" 2>&1
grep -q 'Latest backup: none none' "$test_dir/empty-status.log"

if LITELLM_SMOKE_KEYCHAIN=missing "$command" start > "$test_dir/missing.log" 2>&1; then
  printf 'Missing Keychain item did not stop startup.\n' >&2; exit 1
fi
assert_stopped
if LITELLM_BACKUP_DIR="$test_dir/public" "$command" start > "$test_dir/public.log" 2>&1; then
  printf 'Public backup directory did not stop startup.\n' >&2; exit 1
fi
assert_stopped
if LITELLM_BACKUP_DIR="$test_dir/unwritable" "$command" start > "$test_dir/unwritable.log" 2>&1; then
  printf 'Unwritable backup directory did not stop startup.\n' >&2; exit 1
fi
assert_stopped

"$command" start > "$test_dir/first.log" 2>&1 || { cat "$test_dir/first.log" >&2; exit 1; }
grep -q 'Starting full backup.' "$test_dir/first.log"
grep -q 'LiteLLM is ready' "$test_dir/first.log"
python3 - "$test_dir/first.log" <<'PY'
import pathlib
import sys
lines = pathlib.Path(sys.argv[1]).read_text().splitlines()
assert next(i for i, line in enumerate(lines) if "Starting full backup." in line) < next(
    i for i, line in enumerate(lines) if "LiteLLM is ready" in line
)
PY
[[ "$(compose ps --status running -q proxy)" != '' ]]
[[ "$(count_backups)" == 1 ]]
first_type="$(compose exec -T --user postgres postgres pgbackrest --stanza=litellm info --output=json | python3 -c 'import json,sys; print(json.load(sys.stdin)[0]["backup"][-1]["type"])')"
[[ "$first_type" == full ]]

proxy_id="$(compose ps -q proxy)"
postgres_id="$(compose ps -q postgres)"
for value in 'sk-local-smoke-master-1234567890' 'local-smoke-salt-1234567890' 'local-smoke-postgres-password' 'sk-local-smoke-openrouter'; do
  if "$DOCKER_REAL" inspect "$proxy_id" "$postgres_id" | grep -Fq "$value"; then
    printf 'A secret value appeared in docker inspect.\n' >&2; exit 1
  fi
done

LITELLM_SMOKE_KEYCHAIN=missing "$command" stop > "$test_dir/stop.log" 2>&1
assert_stopped
"$DOCKER_REAL" volume inspect "${COMPOSE_PROJECT_NAME}_postgres-data" >/dev/null
LITELLM_SMOKE_KEYCHAIN=missing "$command" status > "$test_dir/status.log" 2>&1
grep -q 'Latest backup: full' "$test_dir/status.log"

"$command" start > "$test_dir/second.log" 2>&1 || { cat "$test_dir/second.log" >&2; exit 1; }
grep -q 'Starting incr backup.' "$test_dir/second.log"
[[ "$(count_backups)" == 2 ]]
second_type="$(compose exec -T --user postgres postgres pgbackrest --stanza=litellm info --output=json | python3 -c 'import json,sys; print(json.load(sys.stdin)[0]["backup"][-1]["type"])')"
[[ "$second_type" == incr ]]
"$command" start > "$test_dir/third.log" 2>&1
grep -q 'already running' "$test_dir/third.log"
[[ "$(count_backups)" == 2 ]]
if LITELLM_BACKUP_DIR="$test_dir/other-backups" "$command" backup > "$test_dir/mismatched-backup.log" 2>&1; then
  printf 'Backup accepted a path different from the running PostgreSQL mount.\n' >&2; exit 1
fi
grep -q 'Backup directory differs from the running PostgreSQL mount' "$test_dir/mismatched-backup.log"
[[ "$(count_backups)" == 2 ]]
LITELLM_BACKUP_DIR="$test_dir/other-backups" "$command" status > "$test_dir/mismatched-status.log" 2>&1
grep -Fxq "Backup directory: $test_dir/backups" "$test_dir/mismatched-status.log"
if grep -Fxq "Backup directory: $test_dir/other-backups" "$test_dir/mismatched-status.log"; then
  printf 'Status reported the requested path instead of the live mount.\n' >&2; exit 1
fi
"$command" backup > "$test_dir/manual.log" 2>&1
grep -q 'Starting incr backup.' "$test_dir/manual.log"
[[ "$(count_backups)" == 3 ]]

for value in 'sk-local-smoke-master-1234567890' 'local-smoke-salt-1234567890' 'local-smoke-postgres-password' 'sk-local-smoke-openrouter'; do
  if grep -Fq "$value" "$test_dir"/*.log; then
    printf 'A secret value appeared in command output.\n' >&2; exit 1
  fi
  if compose logs --no-color | grep -Fq "$value"; then
    printf 'A secret value appeared in container logs.\n' >&2; exit 1
  fi
done

source "$project_dir/lib/backup.sh"
summary="$(printf '%s' '[{"name":"litellm","backup":[{"type":"full","timestamp":{"stop":1600000000}}]}]' | backup_summary 1600604800)"
[[ "$summary" == *'|full' ]]
summary="$(printf '%s' '[{"name":"litellm","backup":[{"type":"full","timestamp":{"stop":1600000000}}]}]' | backup_summary 1600604799)"
[[ "$summary" == *'|incr' ]]

"$command" stop > "$test_dir/stop2.log" 2>&1
if LITELLM_SMOKE_FAIL_BACKUP=yes "$command" start > "$test_dir/failure.log" 2>&1; then
  printf 'Injected backup failure did not stop startup.\n' >&2; exit 1
fi
assert_stopped
[[ "$(count_backups)" == 3 ]]
printf 'LiteLLM smoke passed: full, incremental, no duplicate, seven-day choice, failure cleanup, live mount check, private backup, and secret boundary.\n'
