#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "[verify] topology + contract regression"

ruby -ryaml -e '
  def fail(msg)
    STDERR.puts("[verify] FAIL: #{msg}")
    exit 1
  end

  mapping_file = "deploy/shared/process_domain_mapping.yaml"
  fail("missing #{mapping_file}") unless File.exist?(mapping_file)

  mapping = YAML.load_file(mapping_file) || {}
  envs = mapping["environments"] || {}
  dev = envs["dev"] || {}
  integration = envs["integration"] || {}
  prod = envs["prod"] || {}

  fail("dev mapping must not be empty") if dev.empty?
  fail("integration mapping must not be empty") if integration.empty?
  fail("prod mapping must not be empty") if prod.empty?

  dev.each do |proc_name, proc_cfg|
    domains = (proc_cfg || {})["domains"] || []
    if domains.size != 1
      fail("dev split-topology violated: #{proc_name} should own exactly one domain, got #{domains.inspect}")
    end
  end

  rec_int = (integration["recommendation-service"] || {})["domains"] || []
  rec_prod = (prod["recommendation-service"] || {})["domains"] || []
  fail("integration recommendation-service must map to [recommendation]") unless rec_int == ["recommendation"]
  fail("prod recommendation-service must map to [recommendation]") unless rec_prod == ["recommendation"]

  %w[integration prod].each do |env|
    process_map = env == "integration" ? integration : prod
    qwq_domains = (process_map["quwoquan_service"] || {})["domains"] || []
    fail("#{env}.quwoquan_service missing") if qwq_domains.empty?
    if qwq_domains.include?("recommendation")
      fail("#{env}.quwoquan_service must not include recommendation domain")
    end
  end
'

SERVICE_YAML="$ROOT/quwoquan_service/contracts/metadata/recommendation/rec_model/service.yaml"
GO_CLIENT="$ROOT/quwoquan_service/services/content-service/internal/infrastructure/recommendation/http_model_client.go"
PY_API="$ROOT/quwoquan_service/services/rec-model-service/api/score.py"

[[ -f "$SERVICE_YAML" ]] || { echo "[verify] FAIL: missing $SERVICE_YAML" >&2; exit 1; }
[[ -f "$GO_CLIENT" ]] || { echo "[verify] FAIL: missing $GO_CLIENT" >&2; exit 1; }
[[ -f "$PY_API" ]] || { echo "[verify] FAIL: missing $PY_API" >&2; exit 1; }

for kw in "domain: recommendation" "path: /v1/score" "path: /health"; do
  if ! grep -n "$kw" "$SERVICE_YAML" >/dev/null 2>&1; then
    echo "[verify] FAIL: service contract missing keyword '$kw'" >&2
    exit 1
  fi
done

if ! grep -n "/v1/score" "$GO_CLIENT" >/dev/null 2>&1; then
  echo "[verify] FAIL: content-service recommendation client route drifted from /v1/score" >&2
  exit 1
fi

for kw in '@router.post("/v1/score"' '@router.get("/health"'; do
  if ! grep -n "$kw" "$PY_API" >/dev/null 2>&1; then
    echo "[verify] FAIL: recommendation-service API route drifted: missing $kw" >&2
    exit 1
  fi
done

echo "[verify] OK: topology + contract regression checked"
