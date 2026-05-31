#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

echo "[verify] acceptance standard (UAT/SIT/GWT/contract + T1~T4)"

ruby -ryaml -e '
  root = Dir.pwd
  ft_root = File.join(root, "specs/feature-tree")
  index_file = File.join(ft_root, "tree_index.yaml")
  abort("[verify] FAIL: missing tree_index.yaml") unless File.exist?(index_file)

  def load_yaml!(path)
    abort("[verify] FAIL: missing #{path}") unless File.exist?(path)
    YAML.load_file(path, permitted_classes: [Time], aliases: true) || {}
  end

  def require_keys!(hash, keys, path)
    keys.each do |key|
      value = hash[key]
      missing = value.nil? || (value.respond_to?(:empty?) && value.empty?)
      abort("[verify] FAIL: #{path} missing #{key}") if missing
    end
  end

  def require_present_keys!(hash, keys, path)
    keys.each do |key|
      abort("[verify] FAIL: #{path} missing #{key}") unless hash.key?(key)
    end
  end

  def validate_evidence!(item, path)
    evidence = item["evidence"] || {}
    primary = evidence["primary"] || []
    abort("[verify] FAIL: #{path} acceptance item missing evidence.primary") unless primary.is_a?(Array) && !primary.empty?
    all = primary + (evidence["supporting"] || [])
    invalid = all.reject { |entry| entry.to_s =~ /\AT[1-4](_|$)/ }
    abort("[verify] FAIL: #{path} evidence must use T1~T4 entries: #{invalid.join(", ")}") unless invalid.empty?

    tests = item["tests"] || {}
    require_present_keys!(tests, %w[planned recorded], path)
  end

  def validate_experience_fields!(group_key, item, path)
    case group_key
    when "uat_acceptance"
      require_present_keys!(item, %w[experience_points performance_points], path)
    when "sit_acceptance"
      require_present_keys!(item, %w[performance_points], path)
    when "gwt_acceptance"
      require_present_keys!(item, %w[contract_refs performance_points], path)
    end
  end

  root_acceptance = load_yaml!(File.join(ft_root, "acceptance.yaml"))
  require_keys!(root_acceptance, %w[version node scope uat_acceptance execution], "app root acceptance")
  (root_acceptance["uat_acceptance"] || {}).each do |id, item|
    require_keys!(item, %w[title done_when evidence tests status], "app root acceptance #{id}")
    validate_evidence!(item, "app root acceptance #{id}")
    validate_experience_fields!("uat_acceptance", item, "app root acceptance #{id}")
  end

  registry = load_yaml!(File.join(ft_root, "journey_scenario_registry.yaml"))
  require_keys!(registry, %w[version journeys scenarios], "journey_scenario_registry.yaml")
  abort("[verify] FAIL: journey_scenario_registry journeys empty") unless registry["journeys"].is_a?(Array) && !registry["journeys"].empty?
  abort("[verify] FAIL: journey_scenario_registry scenarios empty") unless registry["scenarios"].is_a?(Array) && !registry["scenarios"].empty?

  idx = load_yaml!(index_file)
  features = idx["features"] || []

  canonical_groups = {
    "L1_domain_service" => "domain_acceptance",
    "L2_business_capability" => "sit_acceptance",
    "L3_story" => "gwt_acceptance"
  }

  validate_acceptance = lambda do |node, group_key|
    path = File.join(ft_root, node["path"].to_s, "acceptance.yaml")
    acc = load_yaml!(path)
    require_keys!(acc, %w[version node scope execution], path)
    group = acc[group_key]
    abort("[verify] FAIL: #{path} missing #{group_key}") unless group.is_a?(Hash) && !group.empty?
    group.each do |id, item|
      require_keys!(item, %w[title done_when evidence tests status], "#{path} #{id}")
      validate_evidence!(item, "#{path} #{id}")
      validate_experience_fields!(group_key, item, "#{path} #{id}")
    end
  end

  features.each do |l1|
    validate_acceptance.call(l1, "domain_acceptance") if l1["level"].to_s == "L1_domain_service"
    (l1["children"] || []).each do |l2|
      validate_acceptance.call(l2, "sit_acceptance") if l2["level"].to_s == "L2_business_capability"
      (l2["children"] || []).each do |l3|
        validate_acceptance.call(l3, "gwt_acceptance") if l3["level"].to_s == "L3_story" && l2["level"].to_s == "L2_business_capability"
      end
    end
  end

  template_dir = File.join(ft_root, "templates")
  {
    "app_root_acceptance.yaml" => "uat_acceptance",
    "domain_service_acceptance.yaml" => "domain_acceptance",
    "business_capability_acceptance.yaml" => "sit_acceptance",
    "story_acceptance.yaml" => "gwt_acceptance"
  }.each do |name, group|
    path = File.join(template_dir, name)
    acc = load_yaml!(path)
    require_keys!(acc, %w[version node scope execution], path)
    abort("[verify] FAIL: #{path} missing #{group}") unless acc[group].is_a?(Hash) && !acc[group].empty?
  end

  puts "[verify] OK: acceptance standard checked"
'
