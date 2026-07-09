#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

echo "[verify] specs l1 hierarchy"

ruby -ryaml -e '
  root = Dir.pwd
  idx_file = File.join(root, "specs/l1_index.yaml")
  abort("[verify] FAIL: missing specs/l1_index.yaml") unless File.exist?(idx_file)

  idx = YAML.load_file(idx_file) || {}
  nodes = idx["domain_services"] || []
  abort("[verify] FAIL: specs/l1_index.yaml domain_services must be non-empty") unless nodes.is_a?(Array) && !nodes.empty?

  required = (idx.dig("schema", "required_fields") || %w[key title directory category app_modules metadata_domains service_modules deploy_processes test_roots])

  nodes.each do |node|
    required.each do |k|
      v = node[k]
      missing = v.nil? || (v.respond_to?(:empty?) && v.empty?)
      abort("[verify] FAIL: domain_service node missing #{k}: #{node.inspect}") if missing
    end

    category = node["category"].to_s
    abort("[verify] FAIL: invalid category #{category}") unless %w[functional nonfunctional].include?(category)

    dir = File.join(root, node["directory"].to_s)
    abort("[verify] FAIL: domain_service directory not exists: #{node["directory"]}") unless Dir.exist?(dir)
    readme = File.join(dir, "README.md")
    abort("[verify] FAIL: domain_service README missing: #{node["directory"]}/README.md") unless File.exist?(readme)
    spec_file = File.join(dir, "spec.md")
    abort("[verify] FAIL: domain_service spec missing: #{node["directory"]}/spec.md") unless File.exist?(spec_file)

    unless node["directory"].to_s.start_with?("specs/feature-tree/")
      abort("[verify] FAIL: domain_service directory must be under specs/feature-tree/: #{node["directory"]}")
    end
  end

  puts "[verify] OK: #{nodes.size} l1 domain_service nodes checked"
'
