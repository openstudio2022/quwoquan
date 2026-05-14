#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

echo "[verify] specs l1 hierarchy"

ruby -ryaml -e '
  root = Dir.pwd
  idx_file = File.join(root, "specs/l1_index.yaml")
  abort("[verify] FAIL: missing specs/l1_index.yaml") unless File.exist?(idx_file)

  idx = YAML.load_file(idx_file) || {}
  l1 = idx["l1"] || []
  abort("[verify] FAIL: specs/l1_index.yaml l1 must be non-empty") unless l1.is_a?(Array) && !l1.empty?

  l1.each do |node|
    %w[category title key directory feature_path_prefix services].each do |k|
      v = node[k]
      missing = v.nil? || (v.respond_to?(:empty?) && v.empty?)
      abort("[verify] FAIL: l1 node missing #{k}: #{node.inspect}") if missing
    end

    category = node["category"].to_s
    abort("[verify] FAIL: invalid category #{category}") unless %w[functional nonfunctional].include?(category)

    dir = File.join(root, node["directory"].to_s)
    abort("[verify] FAIL: l1 directory not exists: #{node["directory"]}") unless Dir.exist?(dir)
    readme = File.join(dir, "README.md")
    abort("[verify] FAIL: l1 README missing: #{node["directory"]}/README.md") unless File.exist?(readme)
    spec_file = File.join(dir, "spec.md")
    abort("[verify] FAIL: l1 spec missing: #{node["directory"]}/spec.md") unless File.exist?(spec_file)

    unless node["directory"].to_s.start_with?("specs/feature-tree/")
      abort("[verify] FAIL: l1 directory must be under specs/feature-tree/: #{node["directory"]}")
    end
  end

  puts "[verify] OK: #{l1.size} l1 nodes checked"
'
