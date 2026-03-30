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

_verify_entity_dir() {
  local dir="$1"
  local name="$2"
  local has_agg=0 has_entity=0 has_schema=0

  [[ -f "${dir}/aggregate.yaml" ]] && has_agg=1
  [[ -f "${dir}/entity.yaml" ]] && has_entity=1
  [[ -f "${dir}/schema.yaml" ]] && has_schema=1

  if (( has_schema == 1 && has_agg + has_entity == 0 )); then
    ruby -ryaml -e "data = YAML.load_file('${dir}/schema.yaml'); abort('missing dart_class') if data['dart_class'].to_s.strip.empty?; abort('missing output_path') if data['output_path'].to_s.strip.empty?" \
      || { echo "[verify] FAIL: invalid schema metadata ${dir}/schema.yaml"; exit 1; }
    return
  fi

  if (( has_agg + has_entity != 1 )); then
    echo "[verify] FAIL: $name must have exactly one of aggregate.yaml or entity.yaml, or provide schema.yaml for shared contract objects"
    exit 1
  fi

  for f in fields.yaml events.yaml storage.yaml service.yaml; do
    local p="${dir}/${f}"
    if [[ ! -f "$p" ]]; then
      echo "[verify] FAIL: missing $p"
      exit 1
    fi
    ruby -ryaml -e "YAML.load_file('$p')" || { echo "[verify] FAIL: invalid YAML $p"; exit 1; }
  done
}

for dir in "$BASE"/*; do
  [[ -d "$dir" ]] || continue
  name="$(basename "$dir")"
  # Skip reserved/shared prefixes
  [[ "$name" == _* ]] && continue
  # Skip root-level non-entity files we added (entity_catalog, field_policy, etc.)
  [[ -f "$dir" ]] && continue

  # Domain container: no aggregate.yaml/entity.yaml at this level → recurse one level
  if [[ ! -f "${dir}/aggregate.yaml" ]] && [[ ! -f "${dir}/entity.yaml" ]] && [[ ! -f "${dir}/schema.yaml" ]]; then
    for sub in "${dir}"/*; do
      [[ -d "$sub" ]] || continue
      subname="$(basename "$sub")"
      [[ "$subname" == _* ]] && continue
      _verify_entity_dir "$sub" "$name/$subname"
    done
    continue
  fi

  # Entity at top level (legacy/flat layout)
  _verify_entity_dir "$dir" "$name"
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

if command -v python3 >/dev/null 2>&1; then
  python3 "${ROOT}/scripts/verify_link_templates_route_ids.py" || exit 1
fi

echo "[verify] OK: metadata contracts (v3) validated"
