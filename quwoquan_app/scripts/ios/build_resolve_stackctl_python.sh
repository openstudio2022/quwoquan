#!/usr/bin/env bash
set -euo pipefail

# Xcode may expose only its bundled Python, while stackctl requires Python 3.10+
# and PyYAML. Resolve one interpreter before direct Debug constructs a handoff or
# touches Simulator system trust, so every step uses the same compatible runtime.

is_compatible_python() {
  local candidate="$1"
  [[ -x "$candidate" ]] || return 1
  "$candidate" - <<'PY' >/dev/null 2>&1
import sys

if sys.version_info < (3, 10):
    raise SystemExit(1)

import yaml  # noqa: F401
PY
}

if [[ -n "${QWQ_IOS_STACKCTL_PYTHON:-}" ]]; then
  if is_compatible_python "$QWQ_IOS_STACKCTL_PYTHON"; then
    printf '%s\n' "$QWQ_IOS_STACKCTL_PYTHON"
    exit 0
  fi
  echo "[ios-stackctl-python] GATE_BLOCK: QWQ_IOS_STACKCTL_PYTHON must be an executable Python 3.10+ with PyYAML." >&2
  exit 2
fi

PYTHON_CACHE_ROOT="${QWQ_PYTHON_CACHE_ROOT:-${HOME}/.cache/quwoquan/python-envs}"
CANDIDATES=()
if command -v python3 >/dev/null 2>&1; then
  CANDIDATES+=("$(command -v python3)")
fi
CANDIDATES+=(
  "$PYTHON_CACHE_ROOT/quwoquan-data/bin/python3"
  "/opt/homebrew/bin/python3"
  "/usr/local/bin/python3"
)

for candidate in "${CANDIDATES[@]}"; do
  if is_compatible_python "$candidate"; then
    printf '%s\n' "$candidate"
    exit 0
  fi
done

echo "[ios-stackctl-python] GATE_BLOCK: direct Debug requires Python 3.10+ with PyYAML; install the repository runtime or set QWQ_IOS_STACKCTL_PYTHON." >&2
exit 2
