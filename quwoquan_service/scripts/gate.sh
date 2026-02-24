#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "[gate] quwoquan_service quality gate"

fail() {
  echo "[gate] FAIL: $*" 1>&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "missing required command: $1"
}

require_cmd ruby

has_rg() {
  command -v rg >/dev/null 2>&1
}

search() {
  # usage: search "pattern" [paths...]
  local pattern="$1"
  shift
  if has_rg; then
    rg -n "$pattern" "$@"
  else
    # grep fallback: no fancy glob excludes; callers may post-filter.
    grep -R -n -E "$pattern" "$@"
  fi
}

# 1) YAML syntax check (OpenAPI)
echo "[gate] validating OpenAPI yaml syntax"
ruby -ryaml -e 'ARGV.each { |f| YAML.load_file(f) }' \
  contracts/openapi/common.yaml \
  contracts/openapi/*.yaml

# 1.1) OpenAPI <-> endpoint catalog consistency (subset)
echo "[gate] checking OpenAPI <-> endpoint catalog consistency"
ruby -ryaml -e '
  def fail(msg)
    STDERR.puts("[gate] FAIL: #{msg}")
    exit 1
  end

  openapi_files = Dir["contracts/openapi/*.yaml"].reject { |p| p.end_with?("/common.yaml") }
  paths = {}
  openapi_files.each do |f|
    doc = YAML.load_file(f) || {}
    (doc["paths"] || {}).each do |path, ops|
      next unless ops.is_a?(Hash)
      ops.each do |method, _|
        m = method.to_s.upcase
        next unless %w[GET POST PATCH PUT DELETE].include?(m)
        paths["#{m} #{path}"] = true
      end
    end
  end

  catalog = File.read("contracts/endpoint_catalog.md")
  catalog_entries = {}
  catalog.each_line do |line|
    # | `xxx` | GET | `/v1/...` | ...
    if line =~ /\|\s*`[^`]+`\s*\|\s*(GET|POST|PATCH|PUT|DELETE)\s*\|\s*`([^`]+)`\s*\|/
      catalog_entries["#{$1} #{$2}"] = true
    end
  end

  prefixes = %w[/v1/content /v1/user /v1/chat /v1/orch]

  missing_in_catalog = paths.keys.select do |k|
    method, path = k.split(" ", 2)
    prefixes.any? { |p| path.start_with?(p) } && !catalog_entries[k]
  end
  unless missing_in_catalog.empty?
    fail("endpoint_catalog missing entries for OpenAPI paths:\\n" + missing_in_catalog.sort.join("\\n"))
  end

  missing_in_openapi = catalog_entries.keys.select do |k|
    method, path = k.split(" ", 2)
    prefixes.any? { |p| path.start_with?(p) } && !paths[k]
  end
  unless missing_in_openapi.empty?
    fail("endpoint_catalog has entries not present in OpenAPI (for core prefixes):\\n" + missing_in_openapi.sort.join("\\n"))
  end
' 

# 1.2) contracts/README.md must list all contracts/*.md
echo "[gate] checking contracts/README.md coverage"
ruby -e '
  def fail(msg)
    STDERR.puts("[gate] FAIL: #{msg}")
    exit 1
  end
  readme = File.read("contracts/README.md")
  files = Dir["contracts/*.md"].map { |p| File.basename(p) }.reject { |b| b == "README.md" }.sort
  missing = files.reject { |b| readme.include?(b) }
  unless missing.empty?
    fail("contracts/README.md missing entries:\\n" + missing.join("\\n"))
  end
' 

# 1.3) metadata contracts syntax + basic keys
echo "[gate] checking metadata contracts"
ruby -ryaml -e '
  def fail(msg)
    STDERR.puts("[gate] FAIL: #{msg}")
    exit 1
  end

  base = "contracts/metadata"
  files = %w[README.md entity_catalog.yaml field_policy.yaml event_catalog.yaml log_kv_policy.yaml]
  files.each do |f|
    path = File.join(base, f)
    fail("missing #{path}") unless File.exist?(path)
  end

  entities_doc = YAML.load_file(File.join(base, "entity_catalog.yaml")) || {}
  policy_doc = YAML.load_file(File.join(base, "field_policy.yaml")) || {}
  event_doc = YAML.load_file(File.join(base, "event_catalog.yaml")) || {}
  log_kv_doc = YAML.load_file(File.join(base, "log_kv_policy.yaml")) || {}

  entities = entities_doc["entities"] || []
  policies = policy_doc["policies"] || []
  events = event_doc["events"] || []
  log_kv_policies = log_kv_doc["policies"] || []

  fail("entity_catalog.yaml entities is empty") if entities.empty?
  fail("field_policy.yaml policies is empty") if policies.empty?
  fail("event_catalog.yaml events is empty") if events.empty?
  fail("log_kv_policy.yaml policies is empty") if log_kv_policies.empty?

  entity_names = entities.map { |e| e["name"] }.compact
  policies.each do |p|
    fail("field policy missing entity") if p["entity"].to_s.empty?
    fail("unknown entity in field policy: #{p["entity"]}") unless entity_names.include?(p["entity"])
    fail("field policy missing field for #{p["entity"]}") if p["field"].to_s.empty?
    fail("field policy missing classification for #{p["entity"]}.#{p["field"]}") if p["classification"].to_s.empty?
    fail("field policy missing log_policy for #{p["entity"]}.#{p["field"]}") if p["log_policy"].to_s.empty?
  end

  log_kv_policies.each do |p|
    fail("log kv policy missing model") if p["model"].to_s.empty?
    fail("log kv policy missing operation") if p["operation"].to_s.empty?
    input = p["input"] || []
    output = p["output"] || []
    (input + output).each do |item|
      fail("log kv policy item missing key") if item["key"].to_s.empty?
      fail("log kv policy item missing strategy") if item["strategy"].to_s.empty?
    end
  end
' 

# 1.4) runtime/errors contract sync (module/kind enums)
echo "[gate] checking runtime/errors contract sync"
ruby -ryaml -e '
  def fail(msg)
    STDERR.puts("[gate] FAIL: #{msg}")
    exit 1
  end

  openapi = YAML.load_file("contracts/openapi/common.yaml") || {}
  schema = (((openapi["components"] || {})["schemas"] || {})["ErrorResponse"] || {})
  props = schema["properties"] || {}
  module_enum = (props.dig("module", "enum") || []).map(&:to_s).sort
  kind_enum = (props.dig("kind", "enum") || []).map(&:to_s).sort

  go = File.read("runtime/errors/errors.go")
  module_constants = go.scan(/Module[A-Za-z0-9_]+\s+Module\s*=\s*"([A-Z_]+)"/).flatten.sort
  kind_constants = go.scan(/Kind[A-Za-z0-9_]+\s+Kind\s*=\s*"([A-Z_]+)"/).flatten.sort

  unless module_enum == module_constants
    fail("module enum mismatch between openapi common.yaml and runtime/errors/errors.go")
  end
  unless kind_enum == kind_constants
    fail("kind enum mismatch between openapi common.yaml and runtime/errors/errors.go")
  end
'

# 1.5) io access log baseline sync
echo "[gate] checking io access log baseline sync"
ruby -ryaml -e '
  def fail(msg)
    STDERR.puts("[gate] FAIL: #{msg}")
    exit 1
  end

  schema = YAML.load_file("contracts/io_access_log_baseline.yaml") || {}
  required = (schema["required_fields"] || []).map(&:to_s)
  forbidden = (schema["forbidden_fields"] || []).map(&:to_s)

  must_have = %w[
    schemaVersion service timestamp origin direction endpoint sourceId
    traceId requestId sessionId src status durationMs errorCode messageSize
  ]
  must_have.each do |f|
    fail("io_access_log_baseline missing required field: #{f}") unless required.include?(f)
  end

  %w[headers statusCode logType env phase parentTraceId causationId].each do |f|
    fail("io_access_log_baseline missing forbidden field: #{f}") unless forbidden.include?(f)
  end

  go = File.read("runtime/observability/io_access_log.go")
  fail("io_access_log.go missing Origin field") unless go.include?("Origin")
  fail("io_access_log.go missing Direction field") unless go.include?("Direction")
  fail("io_access_log.go should not contain Headers field") if go.include?("Headers")
'

# 1.6) process/exception log baseline sync
echo "[gate] checking process/exception log baseline sync"
ruby -ryaml -e '
  def fail(msg)
    STDERR.puts("[gate] FAIL: #{msg}")
    exit 1
  end

  process_schema = YAML.load_file("contracts/process_trace_log_baseline.yaml") || {}
  exception_schema = YAML.load_file("contracts/exception_log_baseline.yaml") || {}

  process_required = (process_schema["required_fields"] || []).map(&:to_s)
  exception_required = (exception_schema["required_fields"] || []).map(&:to_s)
  process_forbidden = (process_schema["forbidden_fields"] || []).map(&:to_s)
  exception_forbidden = (exception_schema["forbidden_fields"] || []).map(&:to_s)

  %w[schemaVersion service timestamp origin direction endpoint sourceId traceId requestId sessionId src step event result level].each do |f|
    fail("process_trace_log_baseline missing required field: #{f}") unless process_required.include?(f)
  end
  %w[schemaVersion service timestamp origin direction endpoint sourceId traceId requestId sessionId src errorCode errorModule errorKind errorReason userMessage].each do |f|
    fail("exception_log_baseline missing required field: #{f}") unless exception_required.include?(f)
  end
  %w[headers statusCode logType env phase parentTraceId causationId].each do |f|
    fail("process_trace_log_baseline missing forbidden field: #{f}") unless process_forbidden.include?(f)
    fail("exception_log_baseline missing forbidden field: #{f}") unless exception_forbidden.include?(f)
  end

  process_go = File.read("runtime/observability/process_trace_log.go")
  exception_go = File.read("runtime/observability/exception_log.go")
  fail("process_trace_log.go should not contain Headers field") if process_go.include?("Headers")
  fail("exception_log.go should not contain Headers field") if exception_go.include?("Headers")
'

# 2) Ensure deprecated specs are pointers only
echo "[gate] checking deprecated specs are pointers only"
if search "ADDED Requirements|Requirement:" specs/ops-service/spec.md specs/service-ops/spec.md >/dev/null 2>&1; then
  fail "deprecated specs must not contain requirements; keep as pointer only"
fi

# 3) Naming: service-ops must not appear outside deprecated pointers
echo "[gate] checking naming consistency (service-ops)"
if has_rg; then
  if rg -n "service-ops|ServiceOps" . \
    --glob '!.cursor/**' \
    --glob '!scripts/gate.sh' \
    --glob '!specs/service-ops/spec.md' \
    --glob '!specs/ops-service/spec.md' \
    >/dev/null; then
    fail "found service-ops references outside deprecated pointer specs"
  fi
else
  # grep fallback: search everything then filter out the deprecated pointer specs.
  if search "service-ops|ServiceOps" . \
    --exclude-dir .git \
    --exclude-dir .cursor \
    2>/dev/null \
    | grep -v "scripts/gate.sh" \
    | grep -v "specs/service-ops/spec.md" \
    | grep -v "specs/ops-service/spec.md" \
    >/dev/null; then
    fail "found service-ops references outside deprecated pointer specs"
  fi
fi

# 4) No literal '\n' artifacts in docs/contracts
echo "[gate] checking for literal \\n artifacts"
if search "\\\\n[[:space:]]*$" contracts specs platform README.md design.md tasks.md >/dev/null 2>&1; then
  fail "found literal \\n artifacts; please replace with real newlines"
fi

echo "[gate] OK"

