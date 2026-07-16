#!/usr/bin/env bash
# Validate contracts/metadata in v3 layout (per-aggregate / per-entity directories).
# See contracts/metadata/DESIGN.md and the D0/F1 architecture acceptance.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../" && pwd)"
cd "$ROOT"

echo "[verify] contract metadata"

BASE="${ROOT}/quwoquan_service/contracts/metadata"
[[ -d "$BASE" ]] || { echo "[verify] FAIL: missing $BASE"; exit 1; }

# Metadata is consumed by Ruby, Go, and Python. YAML anchors/aliases are not
# portable across their strict loaders, so duplicate small policy mappings
# explicitly instead of relying on parser-specific alias support.
alias_hits="$(find "$BASE" -type f -name '*.yaml' -exec grep -En '(^|[[:space:]])[&*][[:alnum:]_-]+' {} + || true)"
if [[ -n "$alias_hits" ]]; then
  echo "[verify] FAIL: metadata must not contain YAML anchors or aliases"
  printf '%s\n' "$alias_hits"
  exit 1
fi

# 1) Cross-language YAML syntax. Object-specific required-file semantics are
# owned by tools/verify_metadata below; do not duplicate that model here.
for f in _shared/types.yaml _shared/redis_keyspace.yaml; do
  p="${BASE}/${f}"
  [[ -f "$p" ]] || { echo "[verify] FAIL: missing $p"; exit 1; }
done

while IFS= read -r -d '' p; do
  ruby -ryaml -e 'YAML.load_file(ARGV.fetch(0))' "$p" \
    || { echo "[verify] FAIL: invalid YAML $p"; exit 1; }
done < <(find "$BASE" -type f -name '*.yaml' -print0)

# Flat taxonomy fully retired: single source of truth =
# quwoquan_data/control_plane/governance/taxonomy (path-based tagRef).
# tag_taxonomy.yaml /
# tag_ref_migration.yaml must NOT exist; enforced by verify_tag_ref_source_of_truth.py (C1).
for retired in _shared/tag_taxonomy.yaml _shared/tag_ref_migration.yaml; do
  if [[ -f "${BASE}/${retired}" ]]; then
    echo "[verify] FAIL: retired flat taxonomy file still present: ${retired}"; exit 1
  fi
done

if command -v python3 >/dev/null 2>&1; then
  python3 "${ROOT}/quwoquan_app/scripts/runtime/verify_link_templates_route_ids.py" || exit 1
fi

# Go 侧元数据一致性（与 make -C quwoquan_service verify-metadata 对齐）
if command -v go >/dev/null 2>&1; then
  echo "[verify] contract metadata (go verify_metadata)"
  (cd "${ROOT}/quwoquan_service" && go run ./tools/verify_metadata/ contracts/metadata) || exit 1
else
  echo "[verify] WARN: go not found — skipping tools/verify_metadata (run: make -C quwoquan_service verify-metadata)"
fi

echo "[verify] OK: metadata contracts validated"
