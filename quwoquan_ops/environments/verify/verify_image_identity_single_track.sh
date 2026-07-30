#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../" && pwd)"
cd "$ROOT"

echo "[verify] immutable image identity single track"

ruby -ryaml -e '
  root = ARGV[0]
  workloads = Dir[File.join(root, "quwoquan_service", "services", "*")].select { |path| File.directory?(path) }
  platform_ops = File.join(root, "quwoquan_service", "control-plane", "platform-ops")
  workloads << platform_ops if Dir.exist?(platform_ops)

  def fail(message)
    abort("[verify] FAIL: #{message}")
  end

  checked = 0
  workloads.sort.each do |workload|
    name = File.basename(workload)
    owner_name = workload == platform_ops ? "platform-ops-service" : name
    schema_path = File.join(workload, "config", "schema.yaml")
    deployment_path = File.join(workload, "deploy", "base", "deployment.yaml")
    compose_path = File.join(workload, "deploy", "compose.yaml")
    fail("missing config/schema.yaml: #{name}") unless File.file?(schema_path)
    fail("missing deploy/base/deployment.yaml: #{name}") unless File.file?(deployment_path)
    fail("missing deploy/compose.yaml: #{name}") unless File.file?(compose_path)

    governed_sources = Dir[File.join(workload, "{config,cmd,internal}", "**", "*")].select { |path| File.file?(path) }
    governed_sources.each do |source|
      text = File.read(source)
      if text.include?("min_image_version") || text.include?("max_image_version")
        fail("retired image compatibility range found: #{source.delete_prefix(root + "/")}")
      end
    end

    deployment = File.read(deployment_path)
    runtime_name_match = deployment.match(/-\s+name:\s*SERVICE_NAME\s*\n\s+value:\s*([A-Za-z0-9-]+)/)
    fail("deployment missing canonical SERVICE_NAME value: #{name}") unless runtime_name_match
    runtime_name = runtime_name_match[1]
    fail("deployment owner mismatch: #{owner_name} != #{runtime_name}") unless runtime_name == owner_name
    fail("deployment missing package image identity annotation: #{name}") unless deployment.scan("quwoquan.io/image-version: package-required").length >= 2
    fail("deployment image is not package-bound: #{owner_name}") unless deployment.include?("image: quwoquan/#{owner_name}:package-required")
    deployment_payload = YAML.safe_load_file(deployment_path, permitted_classes: [Symbol]) || {}
    containers = deployment_payload.dig("spec", "template", "spec", "containers")
    fail("deployment containers must be a list: #{name}") unless containers.is_a?(Array)
    container = containers.find { |entry| entry.is_a?(Hash) && entry["name"] == owner_name }
    fail("deployment has no owner container: #{name}") unless container
    image_identity = Array(container["env"]).find { |entry| entry.is_a?(Hash) && entry["name"] == "IMAGE_VERSION" }
    field_path = image_identity&.dig("valueFrom", "fieldRef", "fieldPath")
    expected_field_path = "metadata.annotations[" + 39.chr + "quwoquan.io/image-version" + 39.chr + "]"
    unless field_path == expected_field_path
      fail("deployment IMAGE_VERSION is not sourced from its immutable annotation: #{name}")
    end

    compose = YAML.safe_load_file(compose_path, permitted_classes: [Symbol]) || {}
    services = compose["services"]
    fail("compose services must be a map: #{name}") unless services.is_a?(Hash)
    image_key = "QWQ_COMPOSE_#{owner_name.upcase.tr("-", "_")}_IMAGE"
    first_party = services.select { |_workload_name, spec| spec.is_a?(Hash) && spec.key?("build") }
    fail("compose has no first-party build workload: #{name}") if first_party.empty?
    first_party.each do |workload_name, spec|
      image = spec["image"].to_s
      unless image.start_with?("${#{image_key}:?") && image.end_with?("}")
        fail("compose #{workload_name} must require exact #{image_key}: #{name}")
      end
      environment = spec["environment"]
      fail("compose #{workload_name} environment must be a map: #{name}") unless environment.is_a?(Hash)
      identity = environment["IMAGE_VERSION"].to_s
      unless identity.start_with?("${QWQ_COMPOSE_IMAGE_VERSION:?") && identity.end_with?("}")
        fail("compose #{workload_name} must require the canonical image identity: #{name}")
      end
    end
    checked += 1
  end

  package_builder = File.read(File.join(root, "quwoquan_service", "scripts", "runtime", "build_service_env_package.sh"))
  fail("package builder must bind the image digest annotation") unless package_builder.include?(%q{annotations["quwoquan.io/image-version"] = image_digest})
  fail("package builder must bind an OCI digest ref") unless package_builder.include?(%q{container["image"] = f"quwoquan/{service}@{image_digest}"})

  composition = File.read(File.join(root, "quwoquan_ops", "cli", "lib", "immutable_image_composition.py"))
  fail("composition must expose one full digest identity") unless composition.include?("def immutable_image_digest")
  fail("composition must return a sha256 digest") unless composition.include?(%q{digest = f"sha256:{hashlib.sha256(encoded).hexdigest()}"})
  fail("semantic image compatibility must not return") if composition.include?("SemVer") || composition.include?("IMMUTABLE_VERSION_PATTERN")

  fail("unexpected first-party workload count: #{checked}") unless checked == 16
  puts "[verify] OK: #{checked} workloads use one exact immutable image identity; no compatibility ranges"
' "$ROOT"
