#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

echo "[verify] engineering directory"

ruby -ryaml -e '
  root = Dir.pwd
  manifest_file = File.join(root, "specs/engineering_directory_manifest.yaml")
  abort("[verify] FAIL: missing specs/engineering_directory_manifest.yaml") unless File.exist?(manifest_file)

  m = YAML.load_file(manifest_file) || {}

  (m["required_directories"] || []).each do |d|
    path = File.join(root, d)
    abort("[verify] FAIL: missing required directory: #{d}") unless Dir.exist?(path)
  end

  (m["required_files"] || []).each do |f|
    path = File.join(root, f)
    abort("[verify] FAIL: missing required file: #{f}") unless File.file?(path)
  end

  puts "[verify] OK: engineering directory validated"
'
