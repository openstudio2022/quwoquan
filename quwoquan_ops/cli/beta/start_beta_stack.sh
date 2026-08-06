#!/usr/bin/env bash
set -euo pipefail

# Human/IDE compatibility entry only. Candidate selection, topology, package
# identity, ports, Provider runtime and lifecycle are owned by stackctl.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
QWQ_OUTPUT_ROOT="${QWQ_OUTPUT_ROOT:-$ROOT_DIR/.qwq_output}"
export QWQ_OUTPUT_ROOT

usage() {
  cat <<'EOF'
Usage:
  quwoquan_ops/cli/beta/start_beta_stack.sh {up|down|status} [stackctl options]

This is a thin beta-local adapter. It never builds, resolves topology, starts
services or selects data/Provider endpoints itself.

Examples:
  start_beta_stack.sh up --workload full --skip-app
  start_beta_stack.sh down --workload full
  start_beta_stack.sh status --scope config
EOF
}

ACTION="${1:-up}"
if [[ $# -gt 0 ]]; then
  shift
fi

case "$ACTION" in
  up)
    exec env PYTHONDONTWRITEBYTECODE=1 python3 \
      "$ROOT_DIR/quwoquan_ops/cli/stackctl.py" \
      up --target beta-local "$@"
    ;;
  down)
    exec env PYTHONDONTWRITEBYTECODE=1 python3 \
      "$ROOT_DIR/quwoquan_ops/cli/stackctl.py" \
      down --target beta-local "$@"
    ;;
  status|inspect)
    exec env PYTHONDONTWRITEBYTECODE=1 python3 \
      "$ROOT_DIR/quwoquan_ops/cli/stackctl.py" \
      inspect --target beta-local --kind all "$@"
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    echo "GATE_BLOCK: unsupported beta-local action: $ACTION" >&2
    usage >&2
    exit 2
    ;;
esac
