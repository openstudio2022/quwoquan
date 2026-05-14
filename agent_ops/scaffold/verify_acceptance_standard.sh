#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

echo "[verify] acceptance standard"

ruby -ryaml -e '
  root = Dir.pwd
  catalog = YAML.load_file(File.join(root, "changes/feature_catalog.yaml")) || {}
  features = catalog["features"] || []
  statuses_need_artifacts = %w[active release_candidate]

  required_top_keys = %w[version feature_id title template tree_context level_acceptance global_acceptance execution]
  required_groups = %w[
    A1_functional
    A2_experience
    A3_service_governance
    A4_observability
    A5_product_ops
    A6_security_privacy
    A7_contract_metadata_consistency
    A8_test_automation
  ]

  features.each do |f|
    next unless f.is_a?(Hash)
    next unless statuses_need_artifacts.include?(f["status"].to_s)
    slug = f["slug"].to_s
    dirs = Dir[File.join(root, "changes/*-#{slug}")]
    abort("[verify] FAIL: missing feature dir for slug=#{slug}") if dirs.empty?
    dir = dirs.sort.last
    acc_file = File.join(dir, "acceptance.yaml")
    abort("[verify] FAIL: missing acceptance.yaml in #{dir}") unless File.exist?(acc_file)
    acc = YAML.load_file(acc_file) || {}

    required_top_keys.each do |k|
      v = acc[k]
      missing = v.nil? || (v.respond_to?(:empty?) && v.empty?)
      abort("[verify] FAIL: acceptance.yaml missing '#{k}' in #{dir}") if missing
    end

    tc = acc["tree_context"] || {}
    %w[feature_level parent_id acceptance_inherits_from].each do |k|
      v = tc[k]
      missing = v.nil? || v.to_s.strip.empty?
      abort("[verify] FAIL: acceptance.yaml tree_context missing '#{k}' in #{dir}") if missing
    end

    la = acc["level_acceptance"] || {}
    fg = la["focus_groups"]
    missing_fg = !fg.is_a?(Array) || fg.empty?
    abort("[verify] FAIL: acceptance.yaml level_acceptance.focus_groups must be non-empty in #{dir}") if missing_fg
    notes = la["notes"]
    abort("[verify] FAIL: acceptance.yaml level_acceptance.notes missing in #{dir}") if notes.nil? || notes.to_s.strip.empty?

    catalog_level = f["level"].to_s
    if tc["feature_level"].to_s != catalog_level
      abort("[verify] FAIL: acceptance.yaml tree_context.feature_level (#{tc["feature_level"]}) not match catalog level (#{catalog_level}) in #{dir}")
    end
    if tc["parent_id"].to_s != f["parent_id"].to_s
      abort("[verify] FAIL: acceptance.yaml tree_context.parent_id (#{tc["parent_id"]}) not match catalog parent_id (#{f["parent_id"]}) in #{dir}")
    end

    ga = acc["global_acceptance"] || {}
    required_groups.each do |k|
      v = ga[k]
      missing = v.nil? || (v.respond_to?(:empty?) && v.empty?)
      abort("[verify] FAIL: acceptance.yaml global_acceptance missing '#{k}' in #{dir}") if missing
    end

    a1 = ga["A1_functional"] || {}
    scenarios = a1["scenarios"] || []
    abort("[verify] FAIL: acceptance.yaml A1_functional.scenarios must not be empty in #{dir}") if scenarios.empty?

    exec = acc["execution"] || {}
    %w[local_gate full_gate].each do |k|
      v = exec[k]
      missing = v.nil? || v.to_s.strip.empty?
      abort("[verify] FAIL: acceptance.yaml execution missing '#{k}' in #{dir}") if missing
    end
  end

  puts "[verify] OK: acceptance standard checked"
'

