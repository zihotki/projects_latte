#!/usr/bin/env bash

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  printf 'Source this file from a LiteLLM command; do not execute it.\n' >&2
  exit 2
fi

set +x

load_keychain_secret() {
  local name="$1"
  local variable_name="$2"
  local value

  if ! value="$(security find-generic-password -a "$USER" -s "projectslatte.litellm.${name}" -w 2>/dev/null)"; then
    printf 'Missing Keychain item: projectslatte.litellm.%s\n' "$name" >&2
    return 1
  fi

  if [[ -z "$value" ]]; then
    printf 'Empty Keychain item: projectslatte.litellm.%s\n' "$name" >&2
    return 1
  fi

  printf -v "$variable_name" '%s' "$value"
  export "$variable_name"
}

load_keychain_secret master LITELLM_MASTER_KEY \
  && load_keychain_secret salt LITELLM_SALT_KEY \
  && load_keychain_secret postgres POSTGRES_PASSWORD \
  && load_keychain_secret openrouter OPENROUTER_API_KEY \
  || {
    unset LITELLM_MASTER_KEY LITELLM_SALT_KEY POSTGRES_PASSWORD OPENROUTER_API_KEY
    unset -f load_keychain_secret
    return 1
  }

unset -f load_keychain_secret
