#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

domain="${1:-}"
capability="${2:-}"
story="${3:-}"

if [[ -z "$domain" || -z "$capability" || -z "$story" ]]; then
  echo "usage: bash agent_ops/scaffold/new_feature_fullstack.sh <domain-service> <business-capability> <story>" 1>&2
  echo "example: bash agent_ops/scaffold/new_feature_fullstack.sh discovery-content feed-orchestration-recommendation unified-items-cursor" 1>&2
  exit 2
fi

template_dir="specs/feature-tree/templates"
domain_dir="specs/feature-tree/${domain}"
capability_dir="${domain_dir}/${capability}"
story_dir="${capability_dir}/${story}"

mkdir -p "$domain_dir" "$capability_dir" "$story_dir" "specs/changelog"

copy_if_missing() {
  local src="$1"
  local dst="$2"
  if [[ ! -f "$dst" ]]; then
    cp "$src" "$dst"
  fi
}

copy_if_missing "$template_dir/domain_service_spec.md" "$domain_dir/spec.md"
copy_if_missing "$template_dir/domain_service_design.md" "$domain_dir/design.md"
copy_if_missing "$template_dir/domain_service_acceptance.yaml" "$domain_dir/acceptance.yaml"

copy_if_missing "$template_dir/business_capability_spec.md" "$capability_dir/spec.md"
copy_if_missing "$template_dir/business_capability_design.md" "$capability_dir/design.md"
copy_if_missing "$template_dir/business_capability_acceptance.yaml" "$capability_dir/acceptance.yaml"

copy_if_missing "$template_dir/story_spec.md" "$story_dir/spec.md"
copy_if_missing "$template_dir/story_acceptance.yaml" "$story_dir/acceptance.yaml"

if [[ -f "$story_dir/design.md" ]]; then
  echo "[new_feature_fullstack] WARN: Story design.md is not allowed in new model: $story_dir/design.md" 1>&2
fi

if [[ -f "$story_dir/plan.yaml" || -f "$story_dir/tasks.md" ]]; then
  echo "[new_feature_fullstack] WARN: plan.yaml/tasks.md are not formal feature-tree docs in: $story_dir" 1>&2
fi

echo "[new_feature_fullstack] created or verified: $story_dir"
echo "[new_feature_fullstack] next:"
echo "  1. update specs/feature-tree/tree_index.yaml with L1_domain_service / L2_business_capability / L3_story"
echo "  2. update specs/l1_index.yaml if this is a new domain service"
echo "  3. update specs/feature-tree/journey_scenario_registry.yaml if this affects app-level Journey/Scenario"
echo "  4. create or update specs/changelog/CR-YYYYMMDD-NNN-<slug>.yaml"
