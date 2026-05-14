#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../" && pwd)"
cd "$ROOT"

echo "[verify] config gray parallel binding"

SERVICE="content-service"
FROM_CONFIG="v2026.02.27.1"
TO_CONFIG="v2026.02.28.0"
FROM_IMAGE="1.7.2"
TO_IMAGE="1.8.0"

for f in \
  "$ROOT/releases/config/$SERVICE/$FROM_CONFIG.yaml" \
  "$ROOT/releases/config/$SERVICE/$TO_CONFIG.yaml"; do
  if [[ ! -f "$f" ]]; then
    echo "[verify] FAIL: missing release config snapshot: $f" >&2
    exit 1
  fi
done

state_file="$ROOT/.release-state/$SERVICE.state"
audit_file="$ROOT/.release-state/$SERVICE.audit.log"
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

bash "$ROOT/agent_ops/deploy/prod/config_release_gray_rollout.sh" \
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
