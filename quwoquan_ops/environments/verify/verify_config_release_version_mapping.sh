#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../" && pwd)"
cd "$ROOT"

echo "[verify] config release version mapping"

STRICT="${QWQ_CONFIG_GATE_STRICT:-1}"

# Recommended repo path for versioned config snapshots:
#   quwoquan_service/services/<service>/configs/releases/<config_version>.yaml
release_root="$ROOT/quwoquan_service/services"

if [[ ! -d "$release_root" ]]; then
  echo "[verify] WARN: quwoquan_service/services not found (version mapping skipped)"
  if [[ "$STRICT" == "1" ]]; then
    echo "[verify] FAIL: strict mode requires quwoquan_service/services layout" >&2
    exit 1
  fi
  exit 0
fi

failures=0
checked=0
shopt -s nullglob

for svc_dir in "$release_root"/*; do
  [[ -d "$svc_dir" ]] || continue
  svc="$(basename "$svc_dir")"
  release_dir="$svc_dir/configs/releases"
  files=( "$release_dir"/v*.yaml )
  if [[ "${#files[@]}" -eq 0 ]]; then
    if [[ "$STRICT" == "1" ]]; then
      echo "[verify] FAIL: no version files in quwoquan_service/services/$svc/configs/releases" >&2
      failures=$((failures + 1))
    else
      echo "[verify] WARN: no version files in quwoquan_service/services/$svc/configs/releases"
    fi
    continue
  fi

  for f in "${files[@]}"; do
    checked=$((checked + 1))
    bn="$(basename "$f")"
    ver="${bn%.yaml}"
    # Basic version name format: starts with "v"
    if [[ ! "$ver" =~ ^v[0-9] ]]; then
      echo "[verify] FAIL: invalid config version filename: $f (expected v*.yaml)" >&2
      failures=$((failures + 1))
      continue
    fi
    echo "[verify] OK: $svc maps config version $ver -> $f"
  done
done

if [[ "$checked" -eq 0 ]]; then
  echo "[verify] WARN: no config release version files found"
  if [[ "$STRICT" == "1" ]]; then
    echo "[verify] FAIL: strict mode requires at least one versioned config file" >&2
    exit 1
  fi
fi

if [[ "$failures" -gt 0 ]]; then
  echo "[verify] FAIL: version mapping check failed (failures=$failures)" >&2
  exit 1
fi

echo "[verify] OK: config release version mapping checked (files=$checked)"
