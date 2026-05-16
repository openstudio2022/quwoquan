#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../" && pwd)"
cd "$ROOT"

echo "[verify] service config layout"

# Env-split guardrail mode:
# - default strict=1: require full env split layout for all services with configs/
STRICT="${QWQ_CONFIG_GATE_STRICT:-1}"

failures=0
warnings=0
checked=0

services_dir="$ROOT/quwoquan_service/services"
if [[ ! -d "$services_dir" ]]; then
  echo "[verify] FAIL: services directory not found: $services_dir" >&2
  exit 1
fi

shopt -s nullglob
for svc_path in "$services_dir"/*; do
  [[ -d "$svc_path" ]] || continue
  svc="$(basename "$svc_path")"
  cfg_root="$svc_path/configs"

  # Service without configs/ is considered out-of-scope for now (skeleton stage).
  if [[ ! -d "$cfg_root" ]]; then
    echo "[verify] WARN: $svc has no configs/ directory (skipped)"
    warnings=$((warnings + 1))
    if [[ "$STRICT" == "1" ]]; then
      echo "[verify] FAIL: strict mode requires configs/ for all services" >&2
      failures=$((failures + 1))
    fi
    continue
  fi

  checked=$((checked + 1))

  default_file="$cfg_root/default/config.yaml"
  alpha_file="$cfg_root/alpha/config.yaml"
  beta_file="$cfg_root/beta/config.yaml"
  gamma_file="$cfg_root/gamma/config.yaml"
  prod_gray_file="$cfg_root/prod-gray/config.yaml"
  prod_file="$cfg_root/prod/config.yaml"

  if [[ -f "$default_file" && -f "$alpha_file" && -f "$beta_file" && -f "$gamma_file" && -f "$prod_gray_file" && -f "$prod_file" ]]; then
    echo "[verify] OK: $svc config layout complete (default/alpha/beta/gamma/prod-gray/prod)"
    continue
  fi

  echo "[verify] FAIL: $svc missing env-split config layout (default/alpha/beta/gamma/prod-gray/prod)" >&2
  failures=$((failures + 1))
done

if [[ "$failures" -gt 0 ]]; then
  echo "[verify] FAIL: service config layout checks failed (failures=$failures, warnings=$warnings, checked=$checked)" >&2
  exit 1
fi

echo "[verify] OK: service config layout checked (checked=$checked, warnings=$warnings, strict=$STRICT)"
