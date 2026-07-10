#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../" && pwd)"
cd "$ROOT"

echo "[verify] service env contract"

STRICT="${QWQ_CONFIG_GATE_STRICT:-1}"

ruby -e '
  root = ARGV[0]
  strict = ARGV[1] == "1"

  required = %w[APP_ENV SERVICE_NAME CONFIG_VERSION IMAGE_VERSION CONFIG_ROOT]
  manifest_dirs = []
  manifest_dirs.concat(Dir[File.join(root, "quwoquan_service/services/*/{deploy,k8s,.k8s}")])
  manifest_dirs.concat(Dir[File.join(root, "quwoquan_ops/{environments,ci,policies}/**/{deploy,k8s,.k8s}")])
  manifest_dirs.select! { |d| Dir.exist?(d) }
  manifest_dirs.uniq!

  if manifest_dirs.empty?
    puts "[verify] WARN: no service or ops deploy/k8s manifest directory found (skipped)"
    if strict
      abort("[verify] FAIL: strict mode requires manifests to validate env contract")
    end
    exit 0
  end

  files = manifest_dirs.flat_map { |d| Dir[File.join(d, "**", "*.{yaml,yml}")] }.uniq
  if files.empty?
    puts "[verify] WARN: no yaml manifests found under deploy/k8s directories"
    if strict
      abort("[verify] FAIL: strict mode requires yaml manifests to validate env contract")
    end
    exit 0
  end

  failures = 0
  warnings = 0

  required.each do |var|
    found = files.any? do |f|
      content = File.read(f)
      content.match?(/name:\s*#{Regexp.escape(var)}\b/)
    end
    if found
      puts "[verify] OK: found env declaration for #{var}"
    else
      puts "[verify] WARN: missing env declaration for #{var} in deploy manifests"
      warnings += 1
      failures += 1 if strict
    end
  end

  if failures > 0
    abort("[verify] FAIL: env contract check failed (failures=#{failures}, warnings=#{warnings}, strict=#{strict ? 1 : 0})")
  end

  puts "[verify] OK: env contract checked (warnings=#{warnings}, strict=#{strict ? 1 : 0})"
' "$ROOT" "$STRICT"
