#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "[verify] config image compatibility"

STRICT="${QWQ_CONFIG_GATE_STRICT:-1}"

ruby -ryaml -e '
  root = ARGV[0]
  strict = ARGV[1] == "1"
  release_root = File.join(root, "releases/config")

  unless Dir.exist?(release_root)
    puts "[verify] WARN: releases/config not found (compat check skipped)"
    abort("[verify] FAIL: strict mode requires config release files with compat metadata") if strict
    exit 0
  end

  files = Dir[File.join(release_root, "*", "*.yaml")]
  if files.empty?
    puts "[verify] WARN: no release config files found for compatibility check"
    abort("[verify] FAIL: strict mode requires release config files") if strict
    exit 0
  end

  failures = 0
  files.each do |f|
    data = YAML.load_file(f) || {}
    cfg = data["config"].is_a?(Hash) ? data["config"] : {}

    minv = data["min_image_version"] || cfg["min_image_version"]
    maxv = data["max_image_version"] || cfg["max_image_version"]

    if minv.nil? || minv.to_s.strip.empty?
      puts "[verify] FAIL: missing min_image_version in #{f}"
      failures += 1
    end
    if maxv.nil? || maxv.to_s.strip.empty?
      puts "[verify] WARN: missing max_image_version in #{f} (recommended)"
    end
  end

  abort("[verify] FAIL: config image compatibility check failed (failures=#{failures})") if failures > 0
  puts "[verify] OK: config image compatibility checked (files=#{files.size})"
' "$ROOT" "$STRICT"
