#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../" && pwd)"
cd "$ROOT"
QWQ_OUTPUT_ROOT="${QWQ_OUTPUT_ROOT:-$ROOT/.qwq_output}"

echo "[verify] config gray parallel binding"

SERVICE="content-service"
FROM_CONFIG="sha256:$(printf '0%.0s' {1..64})"
FROM_IMAGE="sha256:$(printf '1%.0s' {1..64})"
TO_IMAGE="sha256:$(printf '2%.0s' {1..64})"
PYTHONDONTWRITEBYTECODE=1 python3 "$ROOT/quwoquan_ops/cli/stackctl.py" \
  package --env prod --service "$SERVICE" >/dev/null
TO_CONFIG="$(PYTHONPATH="$ROOT" PYTHONDONTWRITEBYTECODE=1 python3 - "$SERVICE" <<'PY'
import json
import sys
from quwoquan_ops.cli.lib.output_paths import service_deployment_package_dir

path = service_deployment_package_dir("prod", sys.argv[1]) / "provenance.json"
print(json.loads(path.read_text(encoding="utf-8"))["configVersion"])
PY
)"

state_file="$QWQ_OUTPUT_ROOT/env/prod/local/prod-hosted/process/release-state/$SERVICE.state"
audit_file="$QWQ_OUTPUT_ROOT/env/prod/local/prod-hosted/process/release-state/$SERVICE.audit.log"
mkdir -p "$QWQ_OUTPUT_ROOT/env/prod/local/prod-hosted/process/release-state"
backup_state=""
backup_audit=""
if [[ -f "$state_file" ]]; then
  backup_state="$(mktemp)"
  cp "$state_file" "$backup_state"
fi
if [[ -f "$audit_file" ]]; then
  backup_audit="$(mktemp)"
  cp "$audit_file" "$backup_audit"
fi

cleanup() {
  if [[ -n "$backup_state" && -f "$backup_state" ]]; then
    cp "$backup_state" "$state_file"
    rm -f "$backup_state"
  else
    rm -f "$state_file"
  fi
  if [[ -n "$backup_audit" && -f "$backup_audit" ]]; then
    cp "$backup_audit" "$audit_file"
    rm -f "$backup_audit"
  else
    rm -f "$audit_file"
  fi
}
trap cleanup EXIT

bash "$ROOT/quwoquan_ops/cli/prod/config_release_gray_rollout.sh" \
  --service "$SERVICE" \
  --from-image "$FROM_IMAGE" \
  --to-image "$TO_IMAGE" \
  --from-config "$FROM_CONFIG" \
  --to-config "$TO_CONFIG" \
  --step 5 >/dev/null

for kv in \
  "from_image=$FROM_IMAGE" \
  "to_image=$TO_IMAGE" \
  "from_config=$FROM_CONFIG" \
  "to_config=$TO_CONFIG" \
  "step=5"; do
  if ! grep -n "$kv" "$state_file" >/dev/null 2>&1; then
    echo "[verify] FAIL: rollout state missing $kv" >&2
    exit 1
  fi
done

if [[ "$FROM_CONFIG" == "$TO_CONFIG" || "$FROM_IMAGE" == "$TO_IMAGE" ]]; then
  echo "[verify] FAIL: parallel binding requires old/new config+image to differ" >&2
  exit 1
fi

echo "[verify] OK: stable/canary parallel binding is executable"
