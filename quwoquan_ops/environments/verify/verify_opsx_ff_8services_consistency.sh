#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../" && pwd)"
cd "$ROOT"

echo "[verify] service domain layout consistency"

ruby -ryaml -e '
  root = Dir.pwd

  def fail(msg)
    abort("[verify] FAIL: #{msg}")
  end

  service_root = File.join(root, "quwoquan_service", "services")
  contracts_root = File.join(root, "quwoquan_service", "contracts", "metadata")
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

  services = {
    "assistant-service" => "assistant",
    "chat-service" => "messages",
    "circle-service" => "social",
    "content-service" => "content",
    "entity-service" => "entity",
    "integration-service" => "integration",
    "notification-service" => "notification",
    "product-ops-service" => "ops",
    "rec-model-service" => "recommendation",
    "rtc-service" => "rtc",
    "search-service" => "search",
    "tag-service" => "tag",
    "user-service" => "user"
  }

  services.each do |svc, domain|
    svc_dir = File.join(service_root, svc)
    fail("missing service directory: #{svc}") unless Dir.exist?(svc_dir)
    fail("missing service configs/: #{svc}") unless Dir.exist?(File.join(svc_dir, "configs"))
    release_glob = File.join(svc_dir, "configs", "releases", "v*.yaml")
    fail("missing release config: #{svc}") if Dir.glob(release_glob).empty?
    fail("missing metadata domain: #{domain}") unless Dir.exist?(File.join(contracts_root, domain))
  end

  %w[contracts generated runtime services tools scripts].each do |token|
    fail("README.md missing current service domain entry: #{token}") unless readme.include?(token)
  end

  puts "[verify] OK: service domains, release configs, metadata domains and README are aligned"
'
