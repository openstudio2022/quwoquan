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
  alpha = envs["alpha"] || {}
  beta = envs["beta"] || {}
  gamma = envs["gamma"] || {}
  prod_gray = envs["prod-gray"] || {}
  prod = envs["prod"] || {}

  fail("alpha mapping must not be empty") if alpha.empty?
  fail("beta mapping must not be empty") if beta.empty?
  fail("gamma mapping must not be empty") if gamma.empty?
  fail("prod-gray mapping must not be empty") if prod_gray.empty?
  fail("prod mapping must not be empty") if prod.empty?

  alpha.each do |proc_name, proc_cfg|
    domains = (proc_cfg || {})["domains"] || []
    if domains.size != 1
      fail("alpha split-topology violated: #{proc_name} should own exactly one domain, got #{domains.inspect}")
    end
  end

  rec_beta = (beta["recommendation-service"] || {})["domains"] || []
  rec_gamma = (gamma["recommendation-service"] || {})["domains"] || []
  rec_prod_gray = (prod_gray["recommendation-service"] || {})["domains"] || []
  rec_prod = (prod["recommendation-service"] || {})["domains"] || []
  fail("beta recommendation-service must map to [recommendation]") unless rec_beta == ["recommendation"]
  fail("gamma recommendation-service must map to [recommendation]") unless rec_gamma == ["recommendation"]
  fail("prod-gray recommendation-service must map to [recommendation]") unless rec_prod_gray == ["recommendation"]
  fail("prod recommendation-service must map to [recommendation]") unless rec_prod == ["recommendation"]

  {"beta" => beta, "gamma" => gamma, "prod-gray" => prod_gray, "prod" => prod}.each do |env, process_map|
    seed_box_domains = (process_map["seed-box"] || {})["domains"] || []
    fail("#{env}.seed-box missing") if seed_box_domains.empty?
    if seed_box_domains.include?("recommendation")
      fail("#{env}.seed-box must not include recommendation domain")
    end
  end
'

python3 scripts/verify_module_package_mapping.py
python3 scripts/verify_reliable_task_catalog.py
python3 scripts/verify_reliable_task_retention_policy.py

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
