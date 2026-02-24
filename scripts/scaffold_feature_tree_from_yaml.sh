#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

tree_file="${1:-}"
if [[ -z "$tree_file" ]]; then
  echo "usage: bash scripts/scaffold_feature_tree_from_yaml.sh <tree-yaml-path>" 1>&2
  echo "example: bash scripts/scaffold_feature_tree_from_yaml.sh specs/feature-tree/runtime/tree.yaml" 1>&2
  exit 2
fi

if [[ ! -f "$tree_file" ]]; then
  echo "missing tree file: $tree_file" 1>&2
  exit 2
fi

ruby -ryaml -e '
  tree_file = ARGV[0]
  root = Dir.pwd
  data = YAML.load_file(tree_file) || {}
  l1 = data["l1"].to_s
  abort("invalid tree yaml: missing l1") if l1.empty?
  base = File.join(root, "specs/feature-tree", l1)
  Dir.mkdir(base) unless Dir.exist?(base)

  def ensure_file(path, content)
    return if File.exist?(path)
    File.write(path, content)
  end

  def scaffold_node(dir, level, feature)
    Dir.mkdir(dir) unless Dir.exist?(dir)
    ensure_file(File.join(dir, "spec.md"), <<~MD)
      # #{level} 特性：#{feature}

      ## 功能说明
      - 待补充

      ## 约束
      - 待补充

      ## 验收标准
      - 待补充（A1~A8 重点组）
    MD
    ensure_file(File.join(dir, "tasks.md"), <<~MD)
      # 开发任务：#{feature}

      - [ ] contracts-first
      - [ ] metadata 对齐
      - [ ] 实现
      - [ ] 测试（mock/unit/contract/integration/uat）
      - [ ] gate 验证
    MD
    ensure_file(File.join(dir, "acceptance.yaml"), <<~YAML)
      version: 1
      feature: "#{feature}"
      level: "#{level}"
      template: "A1-A8"
      focus_groups: []
      tests:
        mock: []
        unit: []
        contract: []
        integration: []
        uat: []
      execution:
        local_gate: "make gate"
        full_gate: "make gate-full"
    YAML
  end

  l2_nodes = data["l2"] || []
  l2_nodes.each do |l2|
    l2_feature = l2["feature"].to_s
    next if l2_feature.empty?
    l2_dir = File.join(base, l2_feature)
    scaffold_node(l2_dir, "L2", l2_feature)
    (l2["l3"] || []).each do |l3|
      l3_feature = l3["feature"].to_s
      next if l3_feature.empty?
      l3_dir = File.join(l2_dir, l3_feature)
      scaffold_node(l3_dir, "L3", l3_feature)
      (l3["l4"] || []).each do |l4|
        l4_feature = l4["feature"].to_s
        next if l4_feature.empty?
        l4_dir = File.join(l3_dir, l4_feature)
        scaffold_node(l4_dir, "L4", l4_feature)
        (l4["l5"] || []).each do |l5|
          l5_feature = l5["feature"].to_s
          next if l5_feature.empty?
          l5_dir = File.join(l4_dir, l5_feature)
          scaffold_node(l5_dir, "L5", l5_feature)
        end
      end
    end
  end

  puts "[scaffold] OK: #{tree_file}"
' "$tree_file"

