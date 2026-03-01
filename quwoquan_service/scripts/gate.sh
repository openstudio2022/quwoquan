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
# Domain-centric openapi.yaml files live at contracts/metadata/{domain}/openapi.yaml
# contracts/openapi/ retains only common.yaml (shared $ref schemas)
echo "[gate] validating OpenAPI yaml syntax"
ruby -ryaml -e 'ARGV.each { |f| YAML.load_file(f) }' \
  contracts/metadata/_shared/openapi_common.yaml \
  contracts/metadata/*/openapi.yaml

# 1.1) OpenAPI <-> endpoint catalog consistency (subset)
echo "[gate] checking OpenAPI <-> endpoint catalog consistency"
ruby -ryaml -e '
  def fail(msg)
    STDERR.puts("[gate] FAIL: #{msg}")
    exit 1
  end

  # endpoint_catalog.md is superseded by per-domain service.yaml in the new design.
  # Skip this check when the legacy catalog file does not exist.
  unless File.exist?("contracts/endpoint_catalog.md")
    puts "[gate] endpoint_catalog.md not present (replaced by service.yaml) — skipping legacy catalog check"
    exit 0
  end

  openapi_files = Dir["contracts/metadata/*/openapi.yaml"]
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

  openapi = YAML.load_file("contracts/metadata/_shared/openapi_common.yaml") || {}
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

# 5) Feature tree consistency: structure + acceptance baseline integrity
echo "[gate] checking feature tree consistency"
ruby -ryaml -rdate -e '
  def fail(msg)
    STDERR.puts("[gate] FAIL: #{msg}")
    exit 1
  end

  def warn(msg)
    STDERR.puts("[gate] WARN: #{msg}")
  end

  def load_yaml(path)
    YAML.safe_load(File.read(path), permitted_classes: [Time, Date, DateTime, Symbol], symbolize_names: false) || {}
  rescue => e
    nil
  end

  specs_root = File.expand_path("../specs/feature-tree", __dir__)
  exit 0 unless Dir.exist?(specs_root)

  warnings = []
  blocking = []

  # ── 5.1 每个节点目录必须具备四类文档 ──────────────────────────────
  # design.md 仅在实施已开始（tasks.md 含任何 [x]）时强制要求；
  # 纯规划阶段（全部 [ ]）缺少 design.md 仅输出 WARNING。
  always_required = %w[spec.md tasks.md acceptance.yaml]
  Dir.glob("#{specs_root}/**/*.yaml").
    select { |f| File.basename(f) == "acceptance.yaml" }.
    each do |acceptance_path|
      node_dir = File.dirname(acceptance_path)
      node_rel = node_dir.sub(specs_root + "/", "")

      always_required.each do |doc|
        path = File.join(node_dir, doc)
        unless File.exist?(path)
          blocking << "feature tree node missing #{doc}: #{node_rel}"
        end
      end

      # design.md: 实施已开始则 BLOCKING，纯规划则 WARNING
      design_path = File.join(node_dir, "design.md")
      unless File.exist?(design_path)
        tasks_path = File.join(node_dir, "tasks.md")
        tasks_content = File.exist?(tasks_path) ? File.read(tasks_path) : ""
        implementation_started = tasks_content.match?(/^- \[x\]/i)
        if implementation_started
          blocking << "feature tree node missing design.md (implementation started): #{node_rel}"
        else
          warnings << "feature tree node missing design.md (planning stage): #{node_rel}"
        end
      end

      # ── 5.2 acceptance.yaml 结构检查 ────────────────────────────────
      doc = load_yaml(acceptance_path)
      if doc.nil?
        blocking << "acceptance.yaml parse error: #{acceptance_path}"
        next
      end

      feature = doc["feature"].to_s
      level   = doc["level"].to_s

      if feature.empty?
        blocking << "acceptance.yaml missing feature field: #{acceptance_path}"
      end
      if level.empty?
        blocking << "acceptance.yaml missing level field: #{acceptance_path}"
      end

      # ── 5.3 归档前状态检查：无 pending 项 ───────────────────────────
      # 仅当 tasks.md 中所有当前交付任务均为 [x] 时才触发此检查（通过检测 archived 标记）
      tasks_path = File.join(node_dir, "tasks.md")
      tasks_content = File.exist?(tasks_path) ? File.read(tasks_path) : ""
      all_tasks_done = !tasks_content.match?(/^- \[ \]/)  # 当前交付无未完成项

      level_acceptance = doc["level_acceptance"] || {}
      if all_tasks_done && level_acceptance.is_a?(Hash) && !level_acceptance.empty?
        level_acceptance.each do |an, criterion|
          next unless criterion.is_a?(Hash)
          status = criterion["status"].to_s
          if status == "pending"
            blocking << "#{feature}/#{an}: status=pending but all tasks done; set to implemented/waived/deferred (#{acceptance_path})"
          end

          # ── 5.4 tests 链接验证：implemented 项的 tests[] 文件必须存在 ──
          if status == "implemented"
            tests = criterion["tests"] || []
            if tests.empty?
              warnings << "#{feature}/#{an}: status=implemented but tests[] is empty (#{acceptance_path})"
            else
              repo_root = File.expand_path("..", __dir__)
              tests.each do |t|
                next unless t.is_a?(Hash)
                test_file = t["file"].to_s
                next if test_file.empty?
                # Search in both app and service directories
                candidates = [
                  File.join(repo_root, "quwoquan_app", test_file),
                  File.join(repo_root, "quwoquan_service", test_file),
                  File.join(repo_root, test_file),
                ]
                exists = candidates.any? { |p| File.exist?(p) }
                unless exists
                  blocking << "#{feature}/#{an}: tests[].file not found: #{test_file}"
                end
              end
            end
          end
        end
      end
    end

  # ── 5.5 tree_index.yaml 与目录结构双向同步 + lifecycle 一致性 ──────
  service_root = File.expand_path(ARGV[0])   # quwoquan_service/
  index_path   = File.join(specs_root, "tree_index.yaml")
    valid_statuses = %w[specified in_progress completed archived cancelled deprecated planned]

  if File.exist?(index_path)
    index = load_yaml(index_path) || {}
    features = index["features"] || []

    indexed_dirs = []
    check_index = lambda do |nodes|
      nodes.each do |node|
        next unless node.is_a?(Hash)
        rel_path = node["path"].to_s
        status   = node["status"].to_s

        unless rel_path.empty?
          # paths are relative to quwoquan_service/
          abs_path = File.expand_path(rel_path, service_root)
          indexed_dirs << abs_path

          # ① tree_index 引用的目录必须存在（planned 节点目录未创建时为 WARNING）
          unless Dir.exist?(abs_path)
            if status == "planned"
              warnings << "tree_index planned node directory not yet created: #{rel_path}"
            else
              blocking << "tree_index.yaml references non-existent directory: #{rel_path}"
            end
          end
        end

        # ② status 必须是合法值
        unless status.empty? || valid_statuses.include?(status)
          node_id = node["id"].to_s
          blocking << "tree_index.yaml node #{node_id} has invalid status: #{status}"
        end

        # ③ lifecycle 一致性：completed 节点的 acceptance.yaml 必须有 archived: true
        if status == "completed" && !rel_path.empty?
          abs_path = File.expand_path(rel_path, service_root)
          acc = File.join(abs_path, "acceptance.yaml")
          if File.exist?(acc)
            acc_doc = load_yaml(acc) || {}
            unless acc_doc["archived"] == true
              warnings << "tree_index status=completed but acceptance.yaml missing archived:true — #{rel_path}"
            end
          end
        end

        # ④ cancelled/deprecated 节点的 tasks.md 不应有未完成的当前交付任务
        if %w[cancelled deprecated].include?(status) && !rel_path.empty?
          abs_path = File.expand_path(rel_path, service_root)
          tasks_f = File.join(abs_path, "tasks.md")
          if File.exist?(tasks_f)
            tasks_content = File.read(tasks_f)
            if tasks_content.match?(/^- \[ \]/)
              warnings << "#{status} node still has unchecked tasks (consider clearing): #{rel_path}"
            end
          end
        end

        check_index.call(node["children"] || [])
      end
    end
    check_index.call(features)

    # ⑤ 孤儿目录检测：目录存在但不在 tree_index 中
    actual_node_dirs = Dir.glob("#{specs_root}/**/*/").map { |d| d.chomp("/") }
    orphaned = actual_node_dirs.reject { |d| indexed_dirs.include?(d) }
    orphaned.each do |d|
      warnings << "feature tree orphan directory (not in tree_index.yaml): #{d.sub(specs_root + "/", "")}"
    end
  end

  warnings.each { |w| STDERR.puts("[gate] WARN: #{w}") }
  unless blocking.empty?
    STDERR.puts("[gate] FAIL: feature tree consistency check failed:")
    blocking.each { |b| STDERR.puts("  - #{b}") }
    exit 1
  end
' "$(pwd)"

# ── G4-G10: content metadata cross-cutting consistency checks ────────────────

CONTENT_POST_DIR="contracts/metadata/content/post"
SHARED_TYPES="contracts/metadata/_shared/types.yaml"

# G4: errors.yaml codes all covered in tests/mock.yaml
echo "[gate] G4: errors.yaml codes covered in tests/mock.yaml"
if [ -f "$CONTENT_POST_DIR/errors.yaml" ] && [ -f "$CONTENT_POST_DIR/tests/mock.yaml" ]; then
  ruby -ryaml -e '
    errors_doc = YAML.load_file(ARGV[0]) || {}
    mock_doc   = YAML.load_file(ARGV[1]) || {}
    codes = (errors_doc["errors"] || []).map { |e| e["code"] }.compact
    # Collect all string values from error_scenarios (input_code, expected_code, given_code, etc.)
    err_scenarios = (mock_doc["error_scenarios"] || mock_doc["scenarios"] || [])
    mock_codes = err_scenarios.flat_map { |s| s.values.select { |v| v.is_a?(String) } }.compact
    missing = codes.reject { |c| mock_codes.any? { |mc| mc.include?(c) } }
    # Soft check: warn if any code has zero coverage
    if missing.any?
      STDERR.puts("[gate] WARN G4: errors.yaml codes without mock scenarios: #{missing.join(", ")}")
    end
  ' "$CONTENT_POST_DIR/errors.yaml" "$CONTENT_POST_DIR/tests/mock.yaml" || true
fi

# G5: behaviors.yaml batch_route paths ⊆ service.yaml api_routes
echo "[gate] G5: behaviors.yaml batch routes consistent with service.yaml"
if [ -f "$CONTENT_POST_DIR/behaviors.yaml" ] && [ -f "$CONTENT_POST_DIR/service.yaml" ]; then
  ruby -ryaml -e '
    beh    = YAML.load_file(ARGV[0]) || {}
    svc    = YAML.load_file(ARGV[1]) || {}
    routes = {}
    (svc["api_routes"] || []).each do |r|
      next unless r.is_a?(Hash)
      routes["#{r["method"]&.upcase} #{r["path"]}"] = true
    end
    (beh["behavior_events"] || []).each do |ev|
      next unless ev["batch_route"]
      r = ev["batch_route"].strip
      unless routes.key?(r)
        STDERR.puts("[gate] FAIL G5: behavior batch_route #{r} not in service.yaml api_routes")
        exit 1
      end
    end
  ' "$CONTENT_POST_DIR/behaviors.yaml" "$CONTENT_POST_DIR/service.yaml"
fi

# G6: ui_config.yaml contentTypes ⊆ _shared/types.yaml ContentType enum
echo "[gate] G6: ui_config contentTypes valid"
if [ -f "$CONTENT_POST_DIR/ui_config.yaml" ] && [ -f "$SHARED_TYPES" ]; then
  ruby -ryaml -e '
    ui   = YAML.load_file(ARGV[0]) || {}
    shared = YAML.load_file(ARGV[1]) || {}
    valid_types = (shared["enums"]["ContentType"] || []).map(&:to_s)
    (ui["discovery_tabs"] || []).each do |tab|
      ct = tab["content_type"].to_s
      unless valid_types.include?(ct)
        STDERR.puts("[gate] FAIL G6: ui_config content_type \"#{ct}\" not in _shared/types.yaml ContentType enum")
        exit 1
      end
    end
  ' "$CONTENT_POST_DIR/ui_config.yaml" "$SHARED_TYPES"
fi

# G7: tests/contract.yaml scenarios reference service.yaml routes
echo "[gate] G7: contract.yaml scenarios cover service.yaml api_routes"
if [ -f "$CONTENT_POST_DIR/tests/contract.yaml" ] && [ -f "$CONTENT_POST_DIR/service.yaml" ]; then
  ruby -ryaml -e '
    contract = YAML.load_file(ARGV[0]) || {}
    svc      = YAML.load_file(ARGV[1]) || {}
    ops      = (svc["api_routes"] || []).map { |r| r["operation"] }.compact
    covered  = (contract["scenarios"] || []).map { |s| s["operation"] }.compact
    missing  = ops.reject { |op| covered.include?(op) }
    if missing.any?
      STDERR.puts("[gate] WARN G7: service.yaml operations without contract scenarios: #{missing.join(", ")}")
    end
  ' "$CONTENT_POST_DIR/tests/contract.yaml" "$CONTENT_POST_DIR/service.yaml" || true
fi

# G8: PII/SENSITIVE fields declared in privacy.yaml app_log_policy
echo "[gate] G8: PII/SENSITIVE fields have privacy.yaml declarations"
if [ -f "$CONTENT_POST_DIR/fields.yaml" ] && [ -f "$CONTENT_POST_DIR/privacy.yaml" ]; then
  ruby -ryaml -e '
    fields  = YAML.load_file(ARGV[0]) || {}
    privacy = YAML.load_file(ARGV[1]) || {}
    pii_fields = []
    (fields["entities"] || {}).each do |_, ent|
      (ent["fields"] || []).each do |f|
        c = f["classification"].to_s
        pii_fields << f["name"] if %w[PII SENSITIVE].include?(c)
      end
    end
    policy_fields = (privacy["app_log_policy"] || []).map { |p| p["field"] }.compact
    missing = pii_fields.reject { |f| policy_fields.include?(f) }
    if missing.any?
      STDERR.puts("[gate] WARN G8: PII/SENSITIVE fields without privacy.yaml policy: #{missing.join(", ")}")
    end
  ' "$CONTENT_POST_DIR/fields.yaml" "$CONTENT_POST_DIR/privacy.yaml" || true
fi

# G9: behaviors.yaml behavior_event types ⊆ _shared/types.yaml BehaviorEventType
echo "[gate] G9: behavior event types valid"
if [ -f "$CONTENT_POST_DIR/behaviors.yaml" ] && [ -f "$SHARED_TYPES" ]; then
  ruby -ryaml -e '
    beh    = YAML.load_file(ARGV[0]) || {}
    shared = YAML.load_file(ARGV[1]) || {}
    valid_types = (shared["enums"]["BehaviorEventType"] || []).map(&:to_s)
    if valid_types.empty?
      # BehaviorEventType enum not yet declared – skip check
      exit 0
    end
    (beh["behavior_events"] || []).each do |ev|
      t = ev["type"].to_s
      unless valid_types.include?(t)
        STDERR.puts("[gate] WARN G9: behavior_event type \"#{t}\" not in _shared/types.yaml BehaviorEventType enum")
      end
    end
  ' "$CONTENT_POST_DIR/behaviors.yaml" "$SHARED_TYPES" || true
fi

# G10: ui_config feature_flags keys cross-checked (advisory)
echo "[gate] G10: feature_flags integrity (advisory)"
if [ -f "$CONTENT_POST_DIR/ui_config.yaml" ]; then
  ruby -ryaml -e '
    ui = YAML.load_file(ARGV[0]) || {}
    flags = ui["feature_flags"] || []
    dup_keys = flags.map { |f| f["flag"] }.group_by { |k| k }.select { |_, v| v.size > 1 }.keys
    if dup_keys.any?
      STDERR.puts("[gate] FAIL G10: duplicate feature_flag keys in ui_config.yaml: #{dup_keys.join(", ")}")
      exit 1
    end
  ' "$CONTENT_POST_DIR/ui_config.yaml"
fi

# G11: contract.yaml go_func 存在性检查（status:pending 豁免）
echo "[gate] G11: contract.yaml go_func coverage"
if [ -f "$CONTENT_POST_DIR/tests/contract.yaml" ]; then
  ruby -ryaml -e '
    def fail(msg)
      STDERR.puts("[gate] FAIL: #{msg}")
      exit 1
    end

    contract = YAML.load_file(ARGV[0]) || {}
    tests_dir = ARGV[1]

    # Collect all func Test* names from *_test.go files in tests/
    go_funcs = Dir.glob(File.join(tests_dir, "*_test.go")).flat_map do |f|
      File.read(f).scan(/^func (Test\w+)\s*\(/).flatten
    end.uniq

    missing = []
    (contract["scenarios"] || []).each do |s|
      next unless s.is_a?(Hash)
      func_name = s["go_func"].to_s
      next if func_name.empty?
      next if s["status"].to_s == "pending"
      unless go_funcs.include?(func_name)
        missing << "#{func_name} (scenario: #{s["name"]})"
      end
    end

    unless missing.empty?
      fail("contract.yaml go_func declarations without Go test functions:\n" + missing.map { |m| "  - #{m}" }.join("\n"))
    end
  ' "$CONTENT_POST_DIR/tests/contract.yaml" \
    "services/content-service/tests"
fi

# ── L2: content-service contract tests ───────────────────────────────────────
echo "[gate] running content-service contract tests"
go test ./services/content-service/... -count=1 -timeout=120s \
  || fail "content-service go tests failed"

# ── T38: e2e.yaml patrol_flow 文件存在性检查（warn 级别，不 fail）─────────────
# 确保 e2e.yaml 中每个 ui_journey 场景的 patrol_flow 引用文件在 quwoquan_app 中存在。
E2E_YAML="contracts/metadata/content/post/tests/e2e.yaml"
APP_DIR="../quwoquan_app"
if [ -f "$E2E_YAML" ] && command -v grep >/dev/null 2>&1; then
  echo "[gate] checking patrol_flow file references in $E2E_YAML"
  patrol_flows=$(grep "patrol_flow:" "$E2E_YAML" | sed 's/.*patrol_flow: *//')
  for flow in $patrol_flows; do
    flow=$(echo "$flow" | tr -d '[:space:]')
    target="$APP_DIR/$flow"
    if [ ! -f "$target" ]; then
      echo "[gate] WARN: patrol_flow 引用文件不存在: $target"
      echo "[gate] WARN: 请创建该文件或更新 e2e.yaml 中的 patrol_flow 路径"
    else
      echo "[gate] OK: patrol_flow 文件存在: $flow"
    fi
  done
fi

# ── T39: api_contract_runner.dart 场景覆盖率检查（warn 级别）────────────────
# 检查 e2e.yaml 中每个 api_contract 场景在 api_contract_runner.dart 中有 test() 调用。
# 场景名在 test_type: api_contract 之前的 name: 行，用 -B2 反向查找。
RUNNER="$APP_DIR/test/cloud/content/api_contract_runner.dart"
if [ -f "$E2E_YAML" ] && [ -f "$RUNNER" ]; then
  echo "[gate] checking api_contract scenario coverage in $RUNNER"
  # grep -B2 找 test_type: api_contract 的前 2 行，再从中提取 name 字段（保留换行）
  api_names=$(grep -B2 "test_type: api_contract" "$E2E_YAML" \
    | grep "name:" | sed "s/.*name: *//" | sed "s/[[:space:]]*$//" || true)
  if [ -z "$api_names" ]; then
    echo "[gate] INFO: no api_contract scenarios declared in $E2E_YAML"
  else
    echo "$api_names" | while IFS= read -r scenario; do
      [ -z "$scenario" ] && continue
      if ! grep -q "$scenario" "$RUNNER" 2>/dev/null; then
        echo "[gate] WARN: api_contract 场景未在 api_contract_runner.dart 中找到: $scenario"
      else
        echo "[gate] OK: api_contract 场景已覆盖: $scenario"
      fi
    done
  fi
fi

# ── L2: recommendation-service python tests (mandatory) ──────────────────────
echo "[gate] running recommendation-service python tests"
PYTHON_TEST_RUNNER="python3"
if [ -x "services/rec-model-service/.venv/bin/python" ]; then
  PYTHON_TEST_RUNNER="services/rec-model-service/.venv/bin/python"
fi
"$PYTHON_TEST_RUNNER" -m pytest services/rec-model-service/tests -q \
  || fail "recommendation-service python tests failed"

echo "[gate] OK"

