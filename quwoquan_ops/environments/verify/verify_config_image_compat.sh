#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../" && pwd)"
cd "$ROOT"

echo "[verify] config image compatibility"

ruby -ryaml -e '
  root = ARGV[0]
  workloads = Dir[File.join(root, "quwoquan_service", "services", "*")].select { |path| File.directory?(path) }
  platform_ops = File.join(root, "quwoquan_service", "control-plane", "platform-ops")
  workloads << platform_ops if Dir.exist?(platform_ops)

  def fail(message)
    abort("[verify] FAIL: #{message}")
  end

  def version(value, source)
    text = value.to_s.strip
    fail("invalid semantic image version #{text.inspect}: #{source}") unless text.match?(/\A\d+\.\d+\.\d+\z/)
    text.split(".").map(&:to_i)
  end

  checked_bounds = 0
  workloads.sort.each do |workload|
    name = File.basename(workload)
    schema_path = File.join(workload, "config", "schema.yaml")
    deployment_path = File.join(workload, "deploy", "base", "deployment.yaml")
    fail("missing config/schema.yaml: #{name}") unless File.file?(schema_path)
    fail("missing deploy/base/deployment.yaml: #{name}") unless File.file?(deployment_path)
    deployment = File.read(deployment_path)
    runtime_name_match = deployment.match(/-\s+name:\s*SERVICE_NAME\s*\n\s+value:\s*([A-Za-z0-9-]+)/)
    fail("deployment missing canonical SERVICE_NAME value: #{name}") unless runtime_name_match
    runtime_name = runtime_name_match[1]

    schema = YAML.safe_load_file(schema_path, permitted_classes: [Symbol]) || {}
    configs = schema["configs"]
    fail("config/schema.yaml configs must be a list: #{name}") unless configs.is_a?(Array)
    by_key = configs.each_with_object({}) do |entry, result|
      fail("invalid config entry: #{schema_path}") unless entry.is_a?(Hash)
      result[entry["key"].to_s] = entry
    end
    min_key = "sys.#{runtime_name}.config.min_image_version"
    max_key = "sys.#{runtime_name}.config.max_image_version"
    min_entry = by_key[min_key]
    max_entry = by_key[max_key]

    source_mentions_bounds = Dir[File.join(workload, "{cmd,internal}", "**", "*.{go,py}")].any? do |source|
      text = File.read(source)
      text.include?("min_image_version") || text.include?("max_image_version")
    end
    if source_mentions_bounds || min_entry || max_entry
      fail("missing #{min_key}: #{name}") unless min_entry
      fail("missing #{max_key}: #{name}") unless max_entry
      fail("#{min_key} must be a string: #{name}") unless min_entry["type"] == "string"
      fail("#{max_key} must be a string: #{name}") unless max_entry["type"] == "string"
      min_version = version(min_entry["default"], min_key)
      max_version = version(max_entry["default"], max_key)
      fail("image compatibility range is inverted: #{name}") if (min_version <=> max_version) == 1
      checked_bounds += 1
    end

    fail("deployment missing IMAGE_VERSION: #{name}") unless deployment.include?("IMAGE_VERSION")
    fail("deployment missing image-version annotation: #{name}") unless deployment.include?("quwoquan.io/image-version")
    fail("deployment image is not package-bound: #{name}") unless deployment.include?(":package-required")
  end

  fail("no image compatibility bounds found") if checked_bounds.zero?
  puts "[verify] OK: #{workloads.length} package-bound workloads; #{checked_bounds} runtime compatibility ranges validated"
' "$ROOT"
