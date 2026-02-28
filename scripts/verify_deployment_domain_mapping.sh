#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "[verify] deployment domain mapping"

ruby -ryaml -e '
  root = Dir.pwd
  file = File.join(root, "deploy/shared/process_domain_mapping.yaml")
  abort("[verify] FAIL: missing deploy/shared/process_domain_mapping.yaml") unless File.exist?(file)

  data = YAML.load_file(file) || {}
  envs = data["environments"]
  abort("[verify] FAIL: environments must be a map") unless envs.is_a?(Hash) && !envs.empty?

  %w[dev integration prod].each do |env|
    abort("[verify] FAIL: missing environments.#{env}") unless envs[env].is_a?(Hash) && !envs[env].empty?
  end

  normalized = {}

  envs.each do |env, processes|
    used_domains = {}
    normalized[env] = {}

    processes.each do |process_name, process_cfg|
      abort("[verify] FAIL: process name empty in #{env}") if process_name.to_s.strip.empty?

      unless process_name == "quwoquan_service" || process_name.end_with?("-service")
        abort("[verify] FAIL: invalid process name '#{process_name}' in #{env} (expect quwoquan_service or *-service)")
      end

      domains = process_cfg.is_a?(Hash) ? process_cfg["domains"] : nil
      abort("[verify] FAIL: #{env}.#{process_name}.domains must be non-empty array") unless domains.is_a?(Array) && !domains.empty?

      norm_domains = domains.map { |d| d.to_s.strip }.reject(&:empty?)
      abort("[verify] FAIL: #{env}.#{process_name}.domains contains empty value") if norm_domains.size != domains.size

      # process-local duplication
      if norm_domains.uniq.size != norm_domains.size
        abort("[verify] FAIL: duplicated domains within #{env}.#{process_name}")
      end

      # environment-global duplication
      norm_domains.each do |d|
        if used_domains.key?(d)
          abort("[verify] FAIL: domain '#{d}' appears in both #{used_domains[d]} and #{process_name} under #{env}")
        end
        used_domains[d] = process_name
      end

      normalized[env][process_name] = norm_domains.sort
    end
  end

  # integration/prod must keep identical topology mapping
  if normalized["integration"] != normalized["prod"]
    abort("[verify] FAIL: integration and prod process-domain mapping must be identical")
  end

  puts "[verify] OK: deployment mapping validated"
'
