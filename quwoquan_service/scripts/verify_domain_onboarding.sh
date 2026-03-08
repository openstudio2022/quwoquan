#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "$ROOT/.." && pwd)"
cd "$ROOT"

echo "[gate] aggregating domain onboarding readiness"

ruby -ryaml -e '
  def fail(msg)
    STDERR.puts("[gate] FAIL: #{msg}")
    exit 1
  end

  root = ARGV[0]
  repo_root = ARGV[1]
  schema_file = File.join(root, "contracts/metadata/_control_plane/domain_onboarding_schema.yaml")
  domains_dir = File.join(root, "contracts/metadata/_control_plane/domains")
  plane_file = File.join(repo_root, "deploy/shared/process_domain_plane_mapping.yaml")

  fail("missing #{schema_file}") unless File.exist?(schema_file)
  fail("missing #{domains_dir}") unless Dir.exist?(domains_dir)
  fail("missing #{plane_file}") unless File.exist?(plane_file)

  schema = YAML.load_file(schema_file) || {}
  schema_def = schema["schema"] || {}
  statuses = schema_def["acceptance_statuses"] || []
  required_sections = Array(schema_def["required_sections"])
  required_test_layers = Array(schema_def["required_test_layers"])
  required_codegen_targets = Array(schema_def["required_codegen_targets"])
  status_rules = schema_def["status_rules"] || {}
  fail("domain_onboarding_schema acceptance_statuses is empty") if statuses.empty?
  status_rank = {}
  statuses.each_with_index { |s, idx| status_rank[s] = idx }
  legacy_rel = schema.dig("minimum_package", "required_deploy_sources", "legacy").to_s
  legacy_file = File.join(repo_root, legacy_rel)
  fail("missing #{legacy_file}") if legacy_rel.empty? || !File.exist?(legacy_file)

  domain_files = Dir[File.join(domains_dir, "*.yaml")].sort
  fail("no domain onboarding files found") if domain_files.empty?

  plane_doc = YAML.load_file(plane_file) || {}
  envs = plane_doc["environments"] || {}
  fail("plane-aware deployment mapping missing environments") if envs.empty?
  legacy_doc = YAML.load_file(legacy_file) || {}
  legacy_envs = legacy_doc["environments"] || {}
  fail("legacy deployment mapping missing environments") if legacy_envs.empty?

  plane_lookup = Hash.new { |h, k| h[k] = {} }
  process_names = {}
  envs.each do |env, processes|
    next unless processes.is_a?(Hash)
    processes.each do |process_name, cfg|
      process_names[process_name] = true
      bindings = cfg.is_a?(Hash) ? (cfg["bindings"] || []) : []
      bindings.each do |binding|
        domain = binding["domain"].to_s
        planes = binding["planes"] || []
        next if domain.empty?
        plane_lookup[domain][env] ||= {}
        planes.each { |plane| plane_lookup[domain][env][plane] = process_name }
      end
    end
  end
  legacy_lookup = Hash.new { |h, k| h[k] = {} }
  legacy_envs.each do |env, processes|
    next unless processes.is_a?(Hash)
    processes.each do |process_name, cfg|
      process_names[process_name] = true
      domains = cfg.is_a?(Hash) ? Array(cfg["domains"]) : []
      domains.each do |domain|
        next if domain.to_s.empty?
        legacy_lookup[domain.to_s][env] ||= []
        legacy_lookup[domain.to_s][env] << process_name
      end
    end
  end

  required_domains = ["content", "chat", "circle", "user"]
  minimum_template_status = "minimum_test_ready"
  minimum_replica_status = "minimum_test_ready"
  full_plane_domains = ["content", "chat", "circle", "user", "assistant", "integration", "notification", "recommendation", "realtime", "rtc"]
  counts = Hash.new(0)
  domain_reports = []
  seen_domains = {}

  domain_files.each do |file|
    doc = YAML.load_file(file) || {}
    required_sections.each do |section|
      fail("#{file}: missing required section #{section}") unless doc.key?(section)
    end
    domain = doc["domain"].to_s
    fail("#{file}: domain is required") if domain.empty?
    fail("duplicate onboarding domain #{domain}") if seen_domains.key?(domain)
    seen_domains[domain] = true

    status = doc["acceptance_status"].to_s
    fail("#{file}: unknown acceptance_status #{status.inspect}") unless status_rank.key?(status)
    counts[status] += 1
    rule = status_rules[status] || {}

    service_names = Array(doc["service_names"]).map(&:to_s)
    fail("#{file}: service_names cannot be empty") if service_names.empty?
    unknown_services = service_names.reject { |name| process_names.key?(name) }
    fail("#{file}: service_names reference unknown deployment processes: #{unknown_services.join(", ")}") unless unknown_services.empty?

    minimum_package = doc["minimum_package"] || {}
    codegen_targets = Array(minimum_package["codegen_targets"]).map(&:to_s)
    invalid_codegen_targets = codegen_targets.reject { |target| required_codegen_targets.include?(target) }
    fail("#{file}: invalid codegen_targets: #{invalid_codegen_targets.join(", ")}") unless invalid_codegen_targets.empty?
    if rule["require_all_codegen_targets"]
      missing_codegen_targets = required_codegen_targets.reject { |target| codegen_targets.include?(target) }
      fail("#{file}: #{status} requires all required codegen targets, missing #{missing_codegen_targets.join(", ")}") unless missing_codegen_targets.empty?
    end

    test_evidence = minimum_package["test_evidence"] || {}
    required_test_layers.each do |layer|
      fail("#{file}: missing minimum_package.test_evidence.#{layer}") unless test_evidence.key?(layer)
    end
    Array(rule["min_test_layers"]).each do |layer|
      if Array(test_evidence[layer]).empty?
        fail("#{file}: #{status} requires non-empty #{layer} evidence")
      end
    end

    deploy = doc["deployment"] || {}
    plane_domain = deploy["plane_binding_domain"].to_s
    fail("#{file}: deployment.plane_binding_domain is required") if plane_domain.empty?
    fail("#{file}: plane_binding_domain must match domain") unless plane_domain == domain

    %w[dev integration prod].each do |env|
      mapping = plane_lookup[domain][env] || {}
      legacy_mapping = legacy_lookup[domain][env] || []
      if mapping.empty?
        fail("#{file}: domain #{domain} missing plane binding in #{env}")
      end
      if rule["require_plane_binding"] && legacy_mapping.empty?
        fail("#{file}: #{status} requires legacy deployment binding in #{env}")
      end
      if full_plane_domains.include?(domain)
        %w[user-plane platform-control-plane product-control-plane].each do |plane|
          unless mapping.key?(plane)
            fail("#{file}: domain #{domain} missing #{plane} binding in #{env}")
          end
        end
      end
    end
    blocking_gaps = Array(doc["blocking_gaps"]).map(&:to_s).reject(&:empty?)
    if rule["require_blocking_gaps_cleared"] && blocking_gaps.any?
      fail("#{file}: #{status} requires blocking_gaps to be empty")
    end
    next_action =
      if blocking_gaps.any?
        "clear_blockers"
      elsif status == "minimum_test_ready"
        "promote_to_deploy_bound"
      elsif status == "deploy_bound"
        "execute_t3_acceptance"
      elsif status == "integration_pass_with_gaps"
        "resolve_remaining_gaps"
      elsif status == "integration_pass"
        "ready_for_incremental_dev"
      else
        "advance_to_next_status"
      end

    domain_reports << {
      "domain" => domain,
      "status" => status,
      "template_role" => doc["template_role"].to_s,
      "rollout_group" => doc["rollout_group"].to_s,
      "service_names" => service_names,
      "blocking_gaps" => blocking_gaps,
      "next_action" => next_action,
    }
  end

  required_domains.each do |domain|
    fail("missing onboarding file for #{domain}") unless seen_domains.key?(domain)
  end

  content_doc = YAML.load_file(File.join(domains_dir, "content.yaml")) || {}
  if status_rank[content_doc["acceptance_status"]] < status_rank[minimum_template_status]
    fail("content template domain must reach at least #{minimum_template_status}")
  end

  %w[chat circle user].each do |domain|
    doc = YAML.load_file(File.join(domains_dir, "#{domain}.yaml")) || {}
    if status_rank[doc["acceptance_status"]] < status_rank[minimum_replica_status]
      fail("#{domain} replica domain must reach at least #{minimum_replica_status}")
    end
  end

  summary = counts.keys.sort_by { |k| status_rank[k] }.map { |k| "#{k}=#{counts[k]}" }.join(", ")
  puts "[gate] domain onboarding detail:"
  domain_reports.sort_by { |item| [status_rank[item["status"]] || 999, item["domain"]] }.each do |item|
    services = item["service_names"].join("|")
    blocker_text = item["blocking_gaps"].empty? ? "none" : item["blocking_gaps"].join(" / ")
    puts "[gate]   - #{item["domain"]}: status=#{item["status"]} role=#{item["template_role"]} wave=#{item["rollout_group"]} services=#{services} next=#{item["next_action"]} blockers=#{blocker_text}"
  end
  puts "[gate] OK: domain onboarding summary: #{summary}"
' "$ROOT" "$REPO_ROOT"
