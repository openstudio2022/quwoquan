#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../" && pwd)"
cd "$ROOT"

usage() {
  cat <<'EOF'
Usage:
  scripts/report_deployment_mapping_impact.sh [--base-ref <git-ref>]

Behavior:
  - Reads deploy/shared/process_domain_mapping.yaml.
  - Compares with <base-ref>:deploy/shared/process_domain_mapping.yaml when available.
  - Prints impacted environments/domains/process ownership changes.
EOF
}

BASE_REF="HEAD~1"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --base-ref) BASE_REF="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage; exit 2 ;;
  esac
done

echo "[report] deployment mapping impact (base_ref=$BASE_REF)"

ruby -ryaml -e '
  def flatten(doc)
    out = {}
    envs = (doc || {})["environments"] || {}
    envs.each do |env, process_map|
      (process_map || {}).each do |proc_name, cfg|
        ((cfg || {})["domains"] || []).each do |d|
          out[[env.to_s, d.to_s]] = proc_name.to_s
        end
      end
    end
    out
  end

  current_file = ARGV[0]
  base_yaml = ARGV[1]
  base_ref = ARGV[2]

  abort("[report] FAIL: missing #{current_file}") unless File.exist?(current_file)

  current_doc = YAML.load_file(current_file) || {}
  current_map = flatten(current_doc)

  if base_yaml.nil? || base_yaml.strip.empty?
    puts "[report] INFO: base mapping unavailable for #{base_ref}; printing current ownership snapshot"
    current_map.sort.each { |(env, domain), proc| puts "[report] SNAPSHOT #{env} #{domain} -> #{proc}" }
    exit 0
  end

  base_doc = YAML.safe_load(base_yaml) || {}
  base_map = flatten(base_doc)

  keys = (base_map.keys + current_map.keys).uniq.sort
  changes = []
  keys.each do |key|
    old_proc = base_map[key]
    new_proc = current_map[key]
    next if old_proc == new_proc
    env, domain = key
    if old_proc.nil?
      changes << "[report] ADDED    #{env} #{domain}: <none> -> #{new_proc}"
    elsif new_proc.nil?
      changes << "[report] REMOVED  #{env} #{domain}: #{old_proc} -> <none>"
    else
      changes << "[report] CHANGED  #{env} #{domain}: #{old_proc} -> #{new_proc}"
    end
  end

  if changes.empty?
    puts "[report] OK: no mapping ownership changes vs #{base_ref}"
  else
    puts "[report] IMPACT: #{changes.size} ownership changes vs #{base_ref}"
    changes.each { |line| puts line }
  end
' "$ROOT/deploy/shared/process_domain_mapping.yaml" \
  "$(git show "${BASE_REF}:deploy/shared/process_domain_mapping.yaml" 2>/dev/null || true)" \
  "$BASE_REF"

