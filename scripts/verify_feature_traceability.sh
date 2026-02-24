#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "[verify] feature traceability"

ruby -ryaml -e '
  root = Dir.pwd
  catalog_file = File.join(root, "changes/feature_catalog.yaml")
  abort("[verify] FAIL: missing changes/feature_catalog.yaml") unless File.exist?(catalog_file)

  catalog = YAML.load_file(catalog_file) || {}
  taxonomy = catalog["taxonomy"] || {}
  levels = taxonomy["levels"] || []
  expected_levels = %w[L1_capability L2_feature L3_subfeature L4_object_task L5_cross_cutting]
  abort("[verify] FAIL: taxonomy.levels invalid") unless expected_levels.all? { |x| levels.include?(x) }

  features = catalog["features"] || []
  statuses_need_artifacts = %w[active release_candidate]
  required = %w[README.md contracts_delta.md acceptance.yaml tasks.md traceability.yaml]
  checked = 0
  by_id = {}

  features.each do |f|
    next unless f.is_a?(Hash)
    by_id[f["id"].to_s] = f
  end

  features.each do |f|
    next unless f.is_a?(Hash)
    checked += 1
    %w[id slug status priority opsx_change_id level parent_id service_domain].each do |k|
      v = f[k]
      missing = v.nil? || v.to_s.strip.empty?
      abort("[verify] FAIL: feature missing '#{k}': #{f.inspect}") if missing
    end
    unless levels.include?(f["level"].to_s)
      abort("[verify] FAIL: feature '#{f["slug"]}' has invalid level '#{f["level"]}'")
    end
    %w[services app_modules opsx_specs].each do |k|
      v = f[k]
      missing = !v.is_a?(Array) || v.empty?
      abort("[verify] FAIL: feature '#{f["slug"]}' missing non-empty '#{k}'") if missing
    end

    profile = f["delivery_profile"] || {}
    %w[ddd metadata_driven contract_driven].each do |k|
      abort("[verify] FAIL: feature '#{f["slug"]}' delivery_profile.#{k} must be true") unless profile[k] == true
    end

    level = f["level"].to_s
    parent_id = f["parent_id"].to_s
    parent = by_id[parent_id]
    parent_level = parent.is_a?(Hash) ? parent["level"].to_s : nil

    if level == "L1_capability"
      abort("[verify] FAIL: L1 feature '#{f["slug"]}' parent_id must be ROOT") unless parent_id == "ROOT"
    elsif level == "L2_feature"
      abort("[verify] FAIL: L2 feature '#{f["slug"]}' parent must be existing L1_capability") unless parent_level == "L1_capability"
    elsif level == "L3_subfeature"
      abort("[verify] FAIL: L3 feature '#{f["slug"]}' parent must be existing L2_feature") unless parent_level == "L2_feature"
    elsif level == "L4_object_task"
      ok = %w[L3_subfeature L2_feature].include?(parent_level)
      abort("[verify] FAIL: L4 feature '#{f["slug"]}' parent must be existing L3_subfeature or L2_feature") unless ok
    elsif level == "L5_cross_cutting"
      ok = %w[L1_capability L2_feature L3_subfeature L4_object_task].include?(parent_level)
      abort("[verify] FAIL: L5 feature '#{f["slug"]}' parent must be existing L1/L2/L3/L4 feature") unless ok
    end
  end

  features.each do |f|
    next unless f.is_a?(Hash)
    next unless statuses_need_artifacts.include?(f["status"].to_s)
    slug = f["slug"].to_s
    next if slug.empty?
    dirs = Dir[File.join(root, "changes/*-#{slug}")]
    if dirs.empty?
      abort("[verify] FAIL: #{f["status"]} feature slug not found in changes/: #{slug}")
    end
    dir = dirs.sort.last
    required.each do |name|
      p = File.join(dir, name)
      abort("[verify] FAIL: missing #{name} in #{dir}") unless File.exist?(p)
    end

    trace = YAML.load_file(File.join(dir, "traceability.yaml")) || {}
    %w[feature opsx services objects apis metadata cross_cutting tests test_automation].each do |k|
      v = trace[k]
      missing = v.nil? || (v.respond_to?(:empty?) && v.empty?)
      abort("[verify] FAIL: traceability.yaml missing '#{k}' in #{dir}") if missing
    end

    opsx = trace["opsx"] || {}
    %w[change_id specs].each do |k|
      v = opsx[k]
      missing = v.nil? || (v.respond_to?(:empty?) && v.empty?)
      abort("[verify] FAIL: traceability.yaml opsx missing '#{k}' in #{dir}") if missing
    end

    ta = trace["test_automation"] || {}
    %w[mock contract integration uat].each do |k|
      v = ta[k]
      missing = v.nil? || (v.respond_to?(:empty?) && v.empty?)
      abort("[verify] FAIL: traceability.yaml test_automation missing '#{k}' in #{dir}") if missing
    end
  end

  puts "[verify] OK: #{checked} features checked"
'

