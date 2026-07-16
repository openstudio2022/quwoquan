#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../" && pwd)"
cd "$ROOT"

echo "[verify] topology + contract regression"

ruby -ryaml -e '
  def fail(msg)
    STDERR.puts("[verify] FAIL: #{msg}")
    exit 1
  end

  mapping_file = "quwoquan_ops/environments/process_domain_mapping.yaml"
  fail("missing #{mapping_file}") unless File.exist?(mapping_file)

  mapping = YAML.load_file(mapping_file) || {}
  envs = mapping["environments"] || {}
  alpha = envs["alpha"] || {}
  beta = envs["beta"] || {}
  gamma = envs["gamma"] || {}
  prod = envs["prod"] || {}

  fail("alpha mapping must not be empty") if alpha.empty?
  fail("beta mapping must not be empty") if beta.empty?
  fail("gamma mapping must not be empty") if gamma.empty?
  fail("prod mapping must not be empty") if prod.empty?

  alpha.each do |proc_name, proc_cfg|
    domains = (proc_cfg || {})["domains"] || []
    if domains.size != 1
      fail("alpha split-topology violated: #{proc_name} should own exactly one domain, got #{domains.inspect}")
    end
  end

  rec_beta = (beta["recommendation-service"] || {})["domains"] || []
  rec_gamma = (gamma["recommendation-service"] || {})["domains"] || []
  rec_prod = (prod["recommendation-service"] || {})["domains"] || []
  fail("beta recommendation-service must map to [recommendation]") unless rec_beta == ["recommendation"]
  fail("gamma recommendation-service must map to [recommendation]") unless rec_gamma == ["recommendation"]
  fail("prod recommendation-service must map to [recommendation]") unless rec_prod == ["recommendation"]

  {"beta" => beta, "gamma" => gamma, "prod" => prod}.each do |env, process_map|
    seed_box_domains = (process_map["seed-box"] || {})["domains"] || []
    fail("#{env}.seed-box missing") if seed_box_domains.empty?
    if seed_box_domains.include?("recommendation")
      fail("#{env}.seed-box must not include recommendation domain")
    end
  end
'

python3 quwoquan_app/scripts/runtime/verify_module_package_mapping.py
python3 quwoquan_service/scripts/recommendation/verify_reliable_task_catalog.py
python3 quwoquan_service/scripts/recommendation/verify_reliable_task_retention_policy.py

SERVICE_YAML="$ROOT/quwoquan_service/contracts/metadata/recommendation/model_release/service.yaml"
GO_CLIENT="$ROOT/quwoquan_service/services/content-service/internal/infrastructure/recommendation/http_model_client.go"
PY_API="$ROOT/quwoquan_service/services/rec-model-service/api/score.py"

[[ -f "$SERVICE_YAML" ]] || { echo "[verify] FAIL: missing $SERVICE_YAML" >&2; exit 1; }
[[ -f "$GO_CLIENT" ]] || { echo "[verify] FAIL: missing $GO_CLIENT" >&2; exit 1; }
[[ -f "$PY_API" ]] || { echo "[verify] FAIL: missing $PY_API" >&2; exit 1; }

ruby -ryaml -e '
  def fail(msg)
    STDERR.puts("[verify] FAIL: #{msg}")
    exit 1
  end

  metadata = YAML.load_file(ARGV.fetch(0)) || {}
  service = metadata["service"] || {}
  fail("recommendation service domain drifted") unless service["domain"] == "recommendation"
  routes = metadata["api_routes"] || []
  expected = {
    "ScoreRecommendationCandidates" => "/internal/v1/recommendation/model-releases:score",
    "BatchScoreRecommendationCandidates" => "/internal/v1/recommendation/model-releases:batch-score",
  }
  expected.each do |operation, path|
    route = routes.find { |candidate| candidate["operation"] == operation }
    fail("missing #{operation}") unless route
    fail("#{operation} path drifted") unless route["path"] == path
    fail("#{operation} must require service principal") unless route.dig("security", "principal") == "service"
    scopes = route.dig("authorization", "scopes") || []
    fail("#{operation} missing recommendation.model.score") unless scopes.include?("recommendation.model.score")
  end
' "$SERVICE_YAML"

for kw in 'recommendation.model_release.ScoreRecommendationCandidates' 'operationsecurity.ForDomain("recommendation")' 'Authorization'; do
  if ! grep -F -n "$kw" "$GO_CLIENT" >/dev/null 2>&1; then
    echo "[verify] FAIL: content-service generated scoring client missing '$kw'" >&2
    exit 1
  fi
done

for kw in 'SCORE_RECOMMENDATION_CANDIDATES_PATH' 'BATCH_SCORE_RECOMMENDATION_CANDIDATES_PATH' 'ServiceTokenVerifier'; do
  if ! grep -F -n "$kw" "$PY_API" >/dev/null 2>&1; then
    echo "[verify] FAIL: recommendation-service generated scoring route missing '$kw'" >&2
    exit 1
  fi
done

for retired in '/v1/score' '/v1/model/reload' '/v1/model/status'; do
  if grep -F -n "$retired" "$PY_API" >/dev/null 2>&1; then
    echo "[verify] FAIL: recommendation-service retains retired route '$retired'" >&2
    exit 1
  fi
done

echo "[verify] OK: topology + contract regression checked"
