#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "[verify] feature traceability (three-layer)"

ruby -e '
  root = Dir.pwd
  bad_patterns = [
    /L3_component/,
    /L3_subfeature/,
    /L4_/,
    /L5_/,
    /L4_detail/,
    /L4_object_task/
  ]

  files = Dir[
    File.join(root, "specs/feature-tree/**/acceptance.yaml"),
    File.join(root, "specs/feature-tree/tree_index.yaml"),
    File.join(root, "specs/feature-tree/00_FEATURE_TREE_STANDARD.md"),
    File.join(root, "specs/feature-tree/01_FEATURE_TREE_LEVEL_DEFINITIONS.md"),
    File.join(root, "specs/changelog/README.md"),
    File.join(root, ".cursor/commands/*.md"),
    File.join(root, ".cursor/rules/*.mdc"),
    File.join(root, "scripts/new_feature_fullstack.sh"),
    File.join(root, "specs/00_MASTER_DEVELOPMENT_FLOW.md")
  ]

  files.each do |file|
    next unless File.file?(file)
    content = File.read(file)
    bad_patterns.each do |pattern|
      if content.match?(pattern)
        abort("[verify] FAIL: current level found in #{file}: #{pattern.inspect}")
      end
    end
  end

  puts "[verify] OK: no current feature-tree levels found"
'
