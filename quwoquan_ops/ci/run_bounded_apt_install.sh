#!/usr/bin/env bash
set -euo pipefail

readonly MAX_ATTEMPTS=2
readonly DEFAULT_COMMAND_TIMEOUT_SECONDS=80
readonly DEFAULT_KILL_GRACE_SECONDS=10
readonly DEFAULT_RETRY_DELAY_SECONDS=10

# Trigger: Service core and App test shard 0 install their declared Ubuntu
# packages through this runner. Empty/invalid package input fails before sudo;
# mirror, dpkg-lock, package-resolution or timeout failures retry once and then
# emit CI.DEPENDENCY.APT_INSTALL_RETRY_EXHAUSTED. Inspect the per-attempt apt
# output, repair the runner/mirror/package declaration, then rerun the exact job.
# Test-only shorter values are allowed, but never values above production bounds.
command_timeout_seconds="${QWQ_CI_APT_COMMAND_TIMEOUT_SECONDS:-$DEFAULT_COMMAND_TIMEOUT_SECONDS}"
kill_grace_seconds="${QWQ_CI_APT_KILL_GRACE_SECONDS:-$DEFAULT_KILL_GRACE_SECONDS}"
retry_delay_seconds="${QWQ_CI_APT_RETRY_DELAY_SECONDS:-$DEFAULT_RETRY_DELAY_SECONDS}"

require_bounded_integer() {
  local name="$1" value="$2" minimum="$3" maximum="$4"
  if [[ ! "$value" =~ ^[0-9]+$ ]]; then
    echo "GATE_BLOCK: CI.DEPENDENCY.APT_BOUND_INVALID name=$name value=$value allowed=${minimum}-${maximum}" >&2
    exit 2
  fi
  local decimal_value=$((10#$value))
  if (( decimal_value < minimum || decimal_value > maximum )); then
    echo "GATE_BLOCK: CI.DEPENDENCY.APT_BOUND_INVALID name=$name value=$value allowed=${minimum}-${maximum}" >&2
    exit 2
  fi
}

require_bounded_integer commandTimeoutSeconds "$command_timeout_seconds" 1 "$DEFAULT_COMMAND_TIMEOUT_SECONDS"
require_bounded_integer killGraceSeconds "$kill_grace_seconds" 1 "$DEFAULT_KILL_GRACE_SECONDS"
require_bounded_integer retryDelaySeconds "$retry_delay_seconds" 0 "$DEFAULT_RETRY_DELAY_SECONDS"

if (( $# == 0 )); then
  echo "GATE_BLOCK: CI.DEPENDENCY.APT_PACKAGE_SET_EMPTY fix=declare-the-required-package-set" >&2
  exit 2
fi

for package in "$@"; do
  if [[ ! "$package" =~ ^[a-z0-9][a-z0-9.+-]*$ ]]; then
    echo "GATE_BLOCK: CI.DEPENDENCY.APT_PACKAGE_INVALID package=$package fix=use-a-literal-Debian-package-name" >&2
    exit 2
  fi
done

for (( attempt = 1; attempt <= MAX_ATTEMPTS; attempt += 1 )); do
  echo "[ci-dependency] apt attempt ${attempt}/${MAX_ATTEMPTS}; commandTimeout=${command_timeout_seconds}s; killGrace=${kill_grace_seconds}s; packages=$*"
  if sudo timeout --kill-after="${kill_grace_seconds}s" "${command_timeout_seconds}s" \
    bash -c '
      set -euo pipefail
      export DEBIAN_FRONTEND=noninteractive
      apt-get \
        -o Acquire::Retries=3 \
        -o Acquire::http::Timeout=20 \
        -o Acquire::https::Timeout=20 \
        -o DPkg::Lock::Timeout=30 \
        update
      apt-get \
        -o Acquire::Retries=3 \
        -o Acquire::http::Timeout=20 \
        -o Acquire::https::Timeout=20 \
        -o DPkg::Lock::Timeout=30 \
        install -y --no-install-recommends "$@"
    ' qwq-bounded-apt "$@"; then
    exit 0
  else
    status=$?
  fi
  echo "[ci-dependency] apt attempt ${attempt}/${MAX_ATTEMPTS} failed status=${status}" >&2
  if (( attempt < MAX_ATTEMPTS )); then
    sleep "$retry_delay_seconds"
  fi
done

echo "GATE_BLOCK: CI.DEPENDENCY.APT_INSTALL_RETRY_EXHAUSTED attempts=${MAX_ATTEMPTS} commandTimeoutSeconds=${command_timeout_seconds} killGraceSeconds=${kill_grace_seconds} retryDelaySeconds=${retry_delay_seconds} packages=$* fix=inspect-attempt-log-repair-mirror-lock-or-package-and-rerun-exact-job" >&2
exit 2
