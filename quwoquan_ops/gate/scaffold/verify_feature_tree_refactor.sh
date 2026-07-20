#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

echo "[verify] feature-tree refactor (app root + domain/capability/story)"

ruby -ryaml -e '
  root = Dir.pwd
  ft_root = File.join(root, "specs/feature-tree")
  index_file = File.join(ft_root, "tree_index.yaml")

  abort("[verify] FAIL: missing specs/feature-tree/tree_index.yaml") unless File.exist?(index_file)
  retired_tree_files = Dir[File.join(ft_root, "*", "tree.yaml")]
  abort("[verify] FAIL: retired L1 tree.yaml mirrors must not return: #{retired_tree_files.join(", ")}") unless retired_tree_files.empty?

  %w[spec.md design.md acceptance.yaml journey_scenario_registry.yaml].each do |name|
    path = File.join(ft_root, name)
    abort("[verify] FAIL: missing app root #{name}") unless File.exist?(path)
  end

  begin
    idx = YAML.load_file(index_file, permitted_classes: [Time], aliases: true) || {}
  rescue ArgumentError
    idx = YAML.load_file(index_file) || {}
  end
  Dir[File.join(root, "specs/changelog/CR-*.yaml")].sort.each do |path|
    begin
      YAML.parse_file(path)
    rescue Psych::SyntaxError => error
      abort("[verify] FAIL: invalid changelog YAML #{path}: #{error.message}")
    end
  end
  nodes = idx["features"] || []
  abort("[verify] FAIL: tree_index features empty") unless nodes.is_a?(Array) && !nodes.empty?

  canonical_l1 = "L1_domain_service"
  canonical_l2 = "L2_business_capability"
  canonical_l3 = "L3_story"

  def require_file!(dir, name)
    abort("[verify] FAIL: missing #{name} in #{dir}") unless File.exist?(File.join(dir, name))
  end

  def forbid_file!(dir, name)
    abort("[verify] FAIL: #{name} is not a formal feature-tree document in #{dir}") if File.exist?(File.join(dir, name))
  end

  def require_spec_heading!(dir, level)
    first_line = File.open(File.join(dir, "spec.md"), &:readline).strip
    abort("[verify] FAIL: spec heading must start with # #{level} in #{dir}") unless first_line.start_with?("# #{level} ")
  end

  def require_domain_or_capability_docs!(dir, level)
    require_file!(dir, "spec.md")
    require_spec_heading!(dir, level)
    require_file!(dir, "design.md")
    require_file!(dir, "acceptance.yaml")
    forbid_file!(dir, "plan.yaml")
    forbid_file!(dir, "tasks.md")
  end

  def require_story_docs!(dir)
    require_file!(dir, "spec.md")
    require_spec_heading!(dir, "L3")
    require_file!(dir, "acceptance.yaml")
    forbid_file!(dir, "design.md")
    forbid_file!(dir, "plan.yaml")
    forbid_file!(dir, "tasks.md")
  end

  def validate_required_node_keys!(node)
    %w[id name level path status].each do |k|
      abort("[verify] FAIL: missing #{k} in #{node.inspect}") if node[k].to_s.strip.empty?
    end
  end

  nodes.each do |node|
    validate_required_node_keys!(node)
    level = node["level"].to_s
    abort("[verify] FAIL: top level must be #{canonical_l1}: #{node["id"]}") unless level == canonical_l1

    dir = File.expand_path(node["path"], ft_root)
    abort("[verify] FAIL: missing domain directory #{dir}") unless Dir.exist?(dir)
    require_domain_or_capability_docs!(dir, "L1")

    (node["children"] || []).each do |child|
      validate_required_node_keys!(child)
      child_level = child["level"].to_s
      abort("[verify] FAIL: child must be #{canonical_l2}: #{child["id"]}") unless child_level == canonical_l2

      child_dir = File.expand_path(child["path"], ft_root)
      abort("[verify] FAIL: missing capability directory #{child_dir}") unless Dir.exist?(child_dir)
      require_domain_or_capability_docs!(child_dir, "L2")

      story_dirs = Dir[File.join(child_dir, "*")].select { |p| File.directory?(p) }
      story_dirs.each do |story_dir|
        story_name = File.basename(story_dir)
        story = (child["children"] || []).find { |entry| entry["id"] == story_name }
        abort("[verify] FAIL: missing L3 entry for #{story_dir}") unless story
        validate_required_node_keys!(story)

        story_level = story["level"].to_s
        abort("[verify] FAIL: story must be #{canonical_l3}: #{story_name}") unless story_level == canonical_l3

        require_story_docs!(story_dir)

        deep_dirs = Dir[File.join(story_dir, "*")].select { |p| File.directory?(p) }
        abort("[verify] FAIL: L3 node must not have nested directories: #{story_dir}") unless deep_dirs.empty?
      end
    end
  end

  template_dir = File.join(ft_root, "templates")
  %w[
    app_root_spec.md app_root_design.md app_root_acceptance.yaml
    domain_service_spec.md domain_service_design.md domain_service_acceptance.yaml
    business_capability_spec.md business_capability_design.md business_capability_acceptance.yaml
    story_spec.md story_acceptance.yaml
  ].each do |name|
    require_file!(template_dir, name)
  end

  %w[plan.yaml tasks.md l2_journey_acceptance.yaml l3_scenario_acceptance.yaml].each do |name|
    forbid_file!(template_dir, name)
  end

  puts "[verify] OK: feature tree supports AppRoot / L1_domain_service / L2_business_capability / L3_story"
'
