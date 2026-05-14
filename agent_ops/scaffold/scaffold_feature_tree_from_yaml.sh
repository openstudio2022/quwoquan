#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

tree_file="${1:-}"
if [[ -z "$tree_file" ]]; then
  echo "usage: bash agent_ops/scaffold/scaffold_feature_tree_from_yaml.sh <three-layer-yaml>" 1>&2
  echo "example: bash agent_ops/scaffold/scaffold_feature_tree_from_yaml.sh tmp/runtime-stories.yaml" 1>&2
  exit 2
fi

if [[ ! -f "$tree_file" ]]; then
  echo "missing tree file: $tree_file" 1>&2
  exit 2
fi

ruby -ryaml -e '
  data = YAML.load_file(ARGV[0]) || {}
  l1 = data["l1"].to_s
  stories = data["stories"] || []
  abort("invalid tree yaml: missing l1") if l1.empty?
  abort("invalid tree yaml: stories must be an array") unless stories.is_a?(Array)

  root = Dir.pwd
  script = File.join(root, "agent_ops/scaffold/new_feature_fullstack.sh")

  stories.each do |story|
    slug = story.is_a?(Hash) ? story["feature"].to_s : story.to_s
    next if slug.empty?
    system("bash", script, l1, slug) or abort("failed to scaffold #{slug}")
  end

  puts "[scaffold] OK: #{ARGV[0]}"
' "$tree_file"
