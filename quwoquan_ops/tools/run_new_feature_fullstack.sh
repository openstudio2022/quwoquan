#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

domain="${1:-}"
capability="${2:-}"
story="${3:-}"

if [[ -z "$domain" || -z "$capability" || -z "$story" ]]; then
  echo "usage: bash quwoquan_ops/tools/run_new_feature_fullstack.sh <l1> <l2> <l3>" >&2
  exit 2
fi
for node in "$domain" "$capability" "$story"; do
  if [[ ! "$node" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]] || [[ "$node" == *--* ]]; then
    echo "GATE_BLOCK: node id must be kebab-case without --: $node" >&2
    exit 2
  fi
done
if [[ "$capability" == *journey* ]]; then
  echo "GATE_BLOCK: Journey/Scenario belongs in AppRoot spec, not an L2 directory" >&2
  exit 2
fi

template_dir="specs/templates/feature-tree"
domain_dir="specs/feature-tree/$domain"
capability_dir="$domain_dir/$capability"
story_dir="$capability_dir/$story"

mkdir -p "$domain_dir" "$capability_dir" "$story_dir"

copy_if_missing() {
  local source="$1"
  local target="$2"
  if [[ ! -f "$target" ]]; then
    cp "$source" "$target"
  fi
}

copy_if_missing "$template_dir/l1-spec.md" "$domain_dir/spec.md"
copy_if_missing "$template_dir/l1-design.md" "$domain_dir/design.md"
copy_if_missing "$template_dir/l2-spec.md" "$capability_dir/spec.md"
copy_if_missing "$template_dir/l3-spec.md" "$story_dir/spec.md"

echo "[new_feature_fullstack] created or verified: $story_dir"
echo "[new_feature_fullstack] next:"
echo "  1. replace every template placeholder and update parent child links"
echo "  2. add an L2 design only when the README design threshold is met"
echo "  3. update AppRoot/L1/L2 Journey responsibilities when applicable"
echo "  4. run: make verify-feature-tree"
