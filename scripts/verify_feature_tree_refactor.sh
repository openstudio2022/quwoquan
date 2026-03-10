#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "[verify] feature-tree refactor (three-level directories)"

ruby -ryaml -e '
  root = Dir.pwd
  index_file = File.join(root, "specs/feature-tree/tree_index.yaml")
  abort("[verify] FAIL: missing specs/feature-tree/tree_index.yaml") unless File.exist?(index_file)

  idx = YAML.load_file(index_file, permitted_classes: [Time], aliases: true) || {}
  nodes = idx["features"] || []
  abort("[verify] FAIL: tree_index features empty") unless nodes.is_a?(Array) && !nodes.empty?

  nodes.each do |node|
    %w[id name level path status].each do |k|
      abort("[verify] FAIL: missing #{k} in #{node.inspect}") if node[k].to_s.strip.empty?
    end
    abort("[verify] FAIL: top level must be L1_capability: #{node["id"]}") unless node["level"] == "L1_capability"

    dir = File.expand_path(node["path"], File.dirname(index_file))
    abort("[verify] FAIL: missing l1 directory #{dir}") unless Dir.exist?(dir)
    %w[spec.md design.md tasks.md acceptance.yaml].each do |f|
      abort("[verify] FAIL: missing #{f} in #{dir}") unless File.exist?(File.join(dir, f))
    end

    children = node["children"] || []
    children.each do |child|
      abort("[verify] FAIL: child must be L2_feature: #{child["id"]}") unless child["level"] == "L2_feature"
      child_dir = File.expand_path(child["path"], File.dirname(index_file))
      abort("[verify] FAIL: missing l2 directory #{child_dir}") unless Dir.exist?(child_dir)
      %w[spec.md design.md tasks.md acceptance.yaml].each do |f|
        abort("[verify] FAIL: missing #{f} in #{child_dir}") unless File.exist?(File.join(child_dir, f))
      end

      story_dirs = Dir[File.join(child_dir, "*")].select { |p| File.directory?(p) }
      story_dirs.each do |story_dir|
        story_name = File.basename(story_dir)
        story = (child["children"] || []).find { |entry| entry["id"] == story_name }
        abort("[verify] FAIL: missing L3_story entry for #{story_dir}") unless story
        abort("[verify] FAIL: child must be L3_story: #{story_name}") unless story["level"] == "L3_story"
        %w[spec.md design.md tasks.md acceptance.yaml].each do |f|
          abort("[verify] FAIL: missing #{f} in #{story_dir}") unless File.exist?(File.join(story_dir, f))
        end
        deep_dirs = Dir[File.join(story_dir, "*")].select { |p| File.directory?(p) }
        abort("[verify] FAIL: L3_story must not have nested directories: #{story_dir}") unless deep_dirs.empty?
      end
    end
  end

  puts "[verify] OK: feature tree follows L1/L2_feature/L3_story structure"
'
