#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

usage() {
  cat <<'EOF'
Usage:
  scripts/config_release_rollback.sh --service <svc> --to-config-version <vX.Y.Z>

Behavior:
  - Idempotently updates deploy/<service>/deployment.yaml env CONFIG_VERSION.
  - Validates target version file exists in releases/config/<service>/<version>.yaml.
EOF
}

SERVICE=""
TARGET_VERSION=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --service) SERVICE="${2:-}"; shift 2 ;;
    --to-config-version) TARGET_VERSION="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage; exit 2 ;;
  esac
done

if [[ -z "$SERVICE" || -z "$TARGET_VERSION" ]]; then
  echo "FAIL: --service and --to-config-version are required" >&2
  usage
  exit 2
fi

target_file="$ROOT/releases/config/$SERVICE/$TARGET_VERSION.yaml"
if [[ ! -f "$target_file" ]]; then
  echo "FAIL: target config version does not exist: $target_file" >&2
  exit 1
fi

deploy_file="$ROOT/deploy/$SERVICE/deployment.yaml"
if [[ ! -f "$deploy_file" ]]; then
  echo "FAIL: deployment manifest not found: $deploy_file" >&2
  exit 1
fi

state_dir="$ROOT/.release-state"
mkdir -p "$state_dir"
lock_dir="$state_dir/$SERVICE.rollback.lock"
audit_file="$state_dir/$SERVICE.audit.log"

if ! mkdir "$lock_dir" 2>/dev/null; then
  echo "FAIL: rollback lock busy for service=$SERVICE (another rollback in progress)" >&2
  exit 1
fi
trap 'rmdir "$lock_dir" 2>/dev/null || true' EXIT

ruby -e '
  file = ARGV[0]
  target = ARGV[1]
  content = File.read(file)
  unless content.match?(/name:\s*CONFIG_VERSION\b/)
    abort("FAIL: CONFIG_VERSION env not found in #{file}")
  end
  updated = content.gsub(/(name:\s*CONFIG_VERSION\s*\n\s*value:\s*)([^\n]+)/, "\\1#{target}")
  if updated == content
    puts "OK: rollback idempotent (already #{target})"
  else
    File.write(file, updated)
    puts "OK: updated CONFIG_VERSION in #{file} -> #{target}"
  end
' "$deploy_file" "$TARGET_VERSION"

echo "$(date -u +"%Y-%m-%dT%H:%M:%SZ") rollback service=$SERVICE target_config=$TARGET_VERSION deploy_file=$deploy_file" >>"$audit_file"
