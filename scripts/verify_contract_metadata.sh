#!/usr/bin/env bash
# Validate contracts/metadata in v3 layout (per-aggregate / per-entity directories).
# See specs/runtime_gap_analysis_and_plan.md and .cursor/rules (metadata consistency).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "[verify] contract metadata (v3)"

BASE="${ROOT}/quwoquan_service/contracts/metadata"
[[ -d "$BASE" ]] || { echo "[verify] FAIL: missing $BASE"; exit 1; }

# 1) Required shared files
for f in _shared/types.yaml _shared/tag_taxonomy.yaml _shared/redis_keyspace.yaml; do
  p="${BASE}/${f}"
  [[ -f "$p" ]] || { echo "[verify] FAIL: missing $p"; exit 1; }
  ruby -ryaml -e "YAML.load_file('$p')" || { echo "[verify] FAIL: invalid YAML $p"; exit 1; }
done

# 2) Each aggregate/entity directory must have the 5 required files
REQUIRED_FILES="aggregate.yaml entity.yaml fields.yaml events.yaml storage.yaml service.yaml"
# We accept dirs that have either aggregate.yaml OR entity.yaml, plus the other 4
AGGREGATE_OR_ENTITY="aggregate.yaml entity.yaml"
OTHER_REQUIRED="fields.yaml events.yaml storage.yaml service.yaml"

for dir in "$BASE"/*; do
  [[ -d "$dir" ]] || continue
  name="$(basename "$dir")"
  [[ "$name" == _shared ]] && continue
  [[ "$name" == _projections ]] && continue
  [[ "$name" == _vectors ]] && continue

  has_agg=0
  has_entity=0
  if [[ -f "${dir}/aggregate.yaml" ]]; then has_agg=1; fi
  if [[ -f "${dir}/entity.yaml" ]]; then has_entity=1; fi
  if (( has_agg + has_entity != 1 )); then
    echo "[verify] FAIL: $name must have exactly one of aggregate.yaml or entity.yaml"
    exit 1
  fi

  for f in fields.yaml events.yaml storage.yaml service.yaml; do
    p="${dir}/${f}"
    if [[ ! -f "$p" ]]; then
      echo "[verify] FAIL: missing $p"
      exit 1
    fi
    ruby -ryaml -e "YAML.load_file('$p')" || { echo "[verify] FAIL: invalid YAML $p"; exit 1; }
  done
done

# 3) Optional: _projections and _vectors (syntax only if present)
for sub in _projections _vectors; do
  d="${BASE}/${sub}"
  [[ -d "$d" ]] || continue
  for f in "$d"/*.yaml; do
    [[ -f "$f" ]] || continue
    ruby -ryaml -e "YAML.load_file('$f')" || { echo "[verify] FAIL: invalid YAML $f"; exit 1; }
  done
done

echo "[verify] OK: metadata contracts (v3) validated"
