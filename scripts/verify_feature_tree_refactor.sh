#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "[verify] feature-tree refactor"

ruby -ryaml -rdate -e '
  root = Dir.pwd
  index_file = File.join(root, "specs/feature-tree/tree_index.yaml")
  abort("[verify] FAIL: missing specs/feature-tree/tree_index.yaml") unless File.exist?(index_file)
  idx = YAML.load_file(index_file, permitted_classes: [Time, Date, Symbol], aliases: true) || {}
  nodes = idx["l1_features"] || idx["features"] || []
  abort("[verify] FAIL: feature index must be non-empty") unless nodes.is_a?(Array) && !nodes.empty?

  if idx["l1_features"].is_a?(Array)
    runtime_node = nodes.find { |n| n["name"].to_s == "runtime" }
    abort("[verify] FAIL: missing runtime l1 in specs/feature-tree/tree_index.yaml") if runtime_node.nil?
    abort("[verify] FAIL: runtime l1 must be active") unless runtime_node["status"].to_s == "active"
    abort("[verify] FAIL: runtime l1 directory mismatch") unless runtime_node["directory"].to_s == "specs/feature-tree/runtime"

    nodes.each do |n|
      %w[name category status directory].each do |k|
        v = n[k]
        missing = v.nil? || v.to_s.strip.empty?
        abort("[verify] FAIL: l1 node missing #{k}: #{n.inspect}") if missing
      end
      dir = File.join(root, n["directory"])
      # planned can be not scaffolded yet; active must be complete
      if n["status"] == "active"
        abort("[verify] FAIL: active l1 directory missing: #{n["directory"]}") unless Dir.exist?(dir)
        %w[spec.md tree.yaml].each do |f|
          p = File.join(dir, f)
          abort("[verify] FAIL: active l1 missing #{f}: #{n["directory"]}") unless File.exist?(p)
        end
      end
    end
  else
    runtime_node = nodes.find { |n| n["name"].to_s == "runtime" || n["id"].to_s == "runtime" }
    abort("[verify] FAIL: missing runtime node in specs/feature-tree/tree_index.yaml") if runtime_node.nil?

    nodes.each do |n|
      %w[id name level path status].each do |k|
        v = n[k]
        missing = v.nil? || v.to_s.strip.empty?
        abort("[verify] FAIL: feature node missing #{k}: #{n.inspect}") if missing
      end
    end
  end

  %w[
    specs/feature-tree/README.md
    specs/00_AGENT_MASTER_SPEC.md
    scripts/scaffold_feature_tree_from_yaml.sh
  ].each do |p|
    abort("[verify] FAIL: missing #{p}") unless File.exist?(File.join(root, p))
  end

  runtime_dir = File.join(root, "specs/feature-tree/runtime")
  abort("[verify] FAIL: missing runtime directory") unless Dir.exist?(runtime_dir)
  %w[spec.md tree.yaml].each do |f|
    abort("[verify] FAIL: runtime missing #{f}") unless File.exist?(File.join(runtime_dir, f))
  end

  l2_dirs = Dir[File.join(runtime_dir, "*")].select { |p| File.directory?(p) }
  abort("[verify] FAIL: runtime l2 directories must be non-empty") if l2_dirs.empty?
  l2_dirs.each do |d|
    %w[spec.md tasks.md].each do |f|
      abort("[verify] FAIL: runtime l2 missing #{f}: #{d}") unless File.exist?(File.join(d, f))
    end
    acceptance_file = File.join(d, "acceptance.yaml")
    content = File.read(File.join(d, "spec.md")) + File.read(File.join(d, "tasks.md"))
    content += File.read(acceptance_file) if File.exist?(acceptance_file)
    abort("[verify] FAIL: placeholder '待补充' found in #{d}") if content.include?("待补充")
  end

  puts "[verify] OK: #{nodes.size} l1 nodes indexed"
'

