#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "[verify] runtime packaging"

ruby -e '
  root = Dir.pwd
  runtime_root = File.join(root, "quwoquan_service/runtime")
  abort("[verify] FAIL: missing quwoquan_service/runtime") unless Dir.exist?(runtime_root)

  required_dirs = %w[
    config
    errors
    observability
    http
    rpc
    messaging
    governance
    experiments
    learning
  ]

  required_dirs.each do |d|
    dir = File.join(runtime_root, d)
    abort("[verify] FAIL: missing runtime dir: #{d}") unless Dir.exist?(dir)
    go_files = Dir[File.join(dir, "*.go")]
    abort("[verify] FAIL: runtime dir has no go file: #{d}") if go_files.empty?
  end

  readme = File.join(runtime_root, "README.md")
  abort("[verify] FAIL: missing runtime README.md") unless File.file?(readme)

  puts "[verify] OK: runtime package structure validated"
'
