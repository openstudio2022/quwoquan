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

  expected_envs = %w[alpha beta gamma prod-gray prod]
  expected_envs.each do |env|
    abort("[verify] FAIL: missing environments.#{env}") unless envs[env].is_a?(Hash) && !envs[env].empty?
  end

  normalized = {}

  envs.each do |env, processes|
    used_domains = {}
    normalized[env] = {}

    processes.each do |process_name, process_cfg|
      abort("[verify] FAIL: process name empty in #{env}") if process_name.to_s.strip.empty?

      allowed = process_name == "seed-box" || process_name.end_with?("-service") ||
                %w[realtime-gateway livekit-sfu coturn].include?(process_name)
      unless allowed
        abort("[verify] FAIL: invalid process name '#{process_name}' in #{env} (expect seed-box, *-service, realtime-gateway, livekit-sfu, coturn)")
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

  # beta/gamma/prod-gray/prod must keep identical topology mapping.
  %w[gamma prod-gray prod].each do |env|
    if normalized["beta"] != normalized[env]
      abort("[verify] FAIL: beta, gamma, prod-gray and prod process-domain mapping must be identical")
    end
  end

  expected_envs.each do |env|
    rec = normalized[env]["recommendation-service"]
    abort("[verify] FAIL: missing recommendation-service in #{env}") if rec.nil?
    unless rec == ["recommendation"]
      abort("[verify] FAIL: #{env}.recommendation-service must map exactly to domains: [recommendation]")
    end
  end

  normalized.each do |env, process_map|
    seed_box = process_map["seed-box"] || []
    if seed_box.include?("recommendation")
      abort("[verify] FAIL: #{env}.seed-box must not include recommendation domain; keep Python process independent")
    end
  end

  puts "[verify] OK: deployment mapping validated"
'

ruby -ryaml -e '
  root = Dir.pwd
  file = File.join(root, "deploy/shared/process_domain_plane_mapping.yaml")
  abort("[verify] FAIL: missing deploy/shared/process_domain_plane_mapping.yaml") unless File.exist?(file)

  data = YAML.load_file(file) || {}
  planes = data["planes"] || []
  envs = data["environments"] || {}

  abort("[verify] FAIL: process_domain_plane_mapping planes must be non-empty") unless planes.is_a?(Array) && !planes.empty?
  %w[user-plane platform-control-plane product-control-plane].each do |plane|
    abort("[verify] FAIL: process_domain_plane_mapping missing plane #{plane}") unless planes.include?(plane)
  end

  expected_envs = %w[alpha beta gamma prod-gray prod]
  expected_envs.each do |env|
    abort("[verify] FAIL: process_domain_plane_mapping missing environments.#{env}") unless envs[env].is_a?(Hash) && !envs[env].empty?
  end

  normalized = {}
  envs.each do |env, processes|
    normalized[env] = {}
    seen = {}
    processes.each do |process_name, cfg|
      allowed = process_name == "seed-box" || process_name.end_with?("-service") || %w[realtime-gateway livekit-sfu coturn].include?(process_name)
      abort("[verify] FAIL: invalid process name #{process_name} in process_domain_plane_mapping #{env}") unless allowed

      bindings = cfg.is_a?(Hash) ? cfg["bindings"] : nil
      abort("[verify] FAIL: #{env}.#{process_name}.bindings must be a non-empty array") unless bindings.is_a?(Array) && !bindings.empty?

      normalized[env][process_name] = bindings.map do |binding|
        domain = binding["domain"].to_s.strip
        plane_list = (binding["planes"] || []).map { |item| item.to_s.strip }.reject(&:empty?).sort
        abort("[verify] FAIL: #{env}.#{process_name} binding missing domain") if domain.empty?
        abort("[verify] FAIL: #{env}.#{process_name}.#{domain} planes cannot be empty") if plane_list.empty?
        plane_list.each do |plane|
          abort("[verify] FAIL: #{env}.#{process_name}.#{domain} unknown plane #{plane}") unless planes.include?(plane)
          key = "#{domain}##{plane}"
          if seen.key?(key)
            abort("[verify] FAIL: domain-plane #{key} appears in both #{seen[key]} and #{process_name} under #{env}")
          end
          seen[key] = process_name
        end
        {"domain" => domain, "planes" => plane_list}
      end.sort_by { |item| item["domain"] }
    end
  end

  %w[gamma prod-gray prod].each do |env|
    if normalized["beta"] != normalized[env]
      abort("[verify] FAIL: beta, gamma, prod-gray and prod process-domain-plane mapping must be identical")
    end
  end

  puts "[verify] OK: plane-aware deployment mapping validated"
'
