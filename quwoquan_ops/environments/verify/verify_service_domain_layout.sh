#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../" && pwd)"
cd "$ROOT"

echo "[verify] service domain layout consistency"

ruby -ryaml -e '
  root = Dir.pwd

  def fail(message)
    abort("[verify] FAIL: #{message}")
  end

  service_root = File.join(root, "quwoquan_service", "services")
  readme = File.read(File.join(root, "quwoquan_service", "README.md"))

  forbidden = [
    File.join("quwoquan_service", "specs"),
    File.join("quwoquan_service", "design.md"),
    File.join("quwoquan_service", "tasks.md"),
    File.join("quwoquan_service", "工程目录设计.md")
  ]
  forbidden.each do |path|
    fail("historical service spec/doc must be removed: #{path}") if File.exist?(File.join(root, path))
  end

  services = Dir.children(service_root).sort.select do |name|
    File.directory?(File.join(service_root, name))
  end
  fail("no service directories found") if services.empty?

  required_directories = %w[contracts internal generated cmd config deploy environments tests build]
  required_environments = %w[alpha beta gamma prod]

  services.each do |service|
    service_dir = File.join(service_root, service)
    required_directories.each do |directory|
      fail("missing #{directory}/: #{service}") unless Dir.exist?(File.join(service_dir, directory))
    end

    schema = File.join(service_dir, "config", "schema.yaml")
    fail("missing config/schema.yaml: #{service}") unless File.file?(schema)

    domain_selector = File.join(service_dir, "contracts", "domain.yaml")
    fail("missing contracts/domain.yaml: #{service}") unless File.file?(domain_selector)
    payload = YAML.safe_load_file(domain_selector) || {}
    fail("invalid contracts/domain.yaml: #{service}") unless payload.is_a?(Hash) && payload.keys == ["domain"]
    domain = payload["domain"].to_s.strip
    fail("empty contracts domain: #{service}") if domain.empty?
    context_directories = Dir.children(File.join(service_dir, "contracts")).select do |name|
      name != "_shared" && File.directory?(File.join(service_dir, "contracts", name))
    end
    fail("missing owned contract context for domain #{domain}: #{service}") if context_directories.empty?
    context_directories.each do |context|
      object_root = File.join(service_dir, "contracts", context)
      objects = Dir.children(object_root).select do |name|
        File.directory?(File.join(object_root, name))
      end
      fail("contract context has no objects #{context}/: #{service}") if objects.empty?
    end

    required_environments.each do |environment|
      config = File.join(service_dir, "environments", environment, "config.yaml")
      fail("missing environments/#{environment}/config.yaml: #{service}") unless File.file?(config)
    end

    fail("missing deploy/base/: #{service}") unless Dir.exist?(File.join(service_dir, "deploy", "base"))
    fail("missing build/Dockerfile: #{service}") unless File.file?(File.join(service_dir, "build", "Dockerfile"))
  end

  %w[contracts generated runtime services tools scripts].each do |token|
    fail("README.md missing current service domain entry: #{token}") unless readme.include?(token)
  end

  puts "[verify] OK: #{services.length} self-owned service domains, configs and four-environment entries are aligned"
'
