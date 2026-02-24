#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

slug="${1:-}"
if [[ -z "$slug" ]]; then
  echo "usage: bash scripts/new_feature_fullstack.sh <slug>" 1>&2
  echo "example: bash scripts/new_feature_fullstack.sh discovery-feed-v1" 1>&2
  exit 2
fi

date_str="$(date +%F)"
dir="changes/${date_str}-${slug}"
mkdir -p "$dir"

if [[ ! -f "$dir/README.md" ]]; then
  cat >"$dir/README.md" <<'EOF'
# 特性：<填写标题>

## 目标（User Value）
- [ ] <目标1>

## 范围（Bounded Context）
- **云侧服务/对象**：<content/chat/user/orchestrator/...>
- **端侧页面/对象**：<module.object.page/action>
- **接口**：<OpenAPI paths>
- **OpsX 变更**：<opsx-change-id>
- **OpsX 相关规格**：<opsx-spec-a, opsx-spec-b>

## 非目标（明确不做什么）
- [ ] <non-goal>

## 风险与回滚
- **风险**：<risk>
- **回滚**：<rollback plan>

## 里程碑（必须按顺序）
- [ ] 1) contracts-first：先改 `quwoquan_service/contracts/openapi/*.yaml` 与相关 contracts
- [ ] 2) specs：更新 `quwoquan_service/specs/*`
- [ ] 3) tasks：更新 `quwoquan_service/tasks.md`（引用 §0 全服务统一能力）+ 端侧任务
- [ ] 4) TDD：先写测试，再实现（单测/契约测/集成测）
- [ ] 5) gate：本地 `make gate` + CI required checks 全绿才允许合入

EOF
fi

if [[ ! -f "$dir/contracts_delta.md" ]]; then
  cat >"$dir/contracts_delta.md" <<'EOF'
# Contracts Delta（contracts-first，必须先完成）

## 云侧 contracts（必需）
- [ ] OpenAPI：`quwoquan_service/contracts/openapi/<service>.v1.yaml`
- [ ] 通用 headers/分页/错误：`quwoquan_service/contracts/openapi/common.yaml`
- [ ] endpoint 归因：`quwoquan_service/contracts/endpoint_catalog.md`
- [ ] 错误码：`quwoquan_service/contracts/error_codes.md`
- [ ] 隐私/安全分级：`quwoquan_service/contracts/privacy_and_security.md`

## 端侧契约对齐（必需）
- [ ] RemoteRepository 不允许“猜字段”：对齐 `items/nextCursor` 等统一结构
- [ ] headers 注入：traceId/requestId/pageId/session/device/appVersion（见 `quwoquan_app/lib/cloud/runtime/cloud_request_headers.dart`）

EOF
fi

if [[ ! -f "$dir/acceptance.yaml" ]]; then
  cat >"$dir/acceptance.yaml" <<'EOF'
version: 1
feature_id: "<Fxxx>"
title: "<feature-title>"
template: "A1-A8"
tree_context:
  feature_level: "<L1_capability|L2_feature|L3_subfeature|L4_object_task|L5_cross_cutting>"
  feature_path: "<capability.xxx.feature.xxx>"
  parent_path: "<capability.xxx>"
  parent_id: "<parent-feature-id>"
  acceptance_inherits_from: "<parent-feature-path-or-id>"
level_acceptance:
  focus_groups: []
  notes: "<level-specific acceptance focus>"
global_acceptance:
  A1_functional:
    scenarios:
      - id: "A1-S1"
        title: "<title>"
        given: "<precondition>"
        when: "<action>"
        then: "<expected_result>"
  A2_experience:
    performance_target: "<TTCR/p95/latency target>"
    stability_target: "<crash/error rate target>"
    ux_target: "<journey usability target>"
  A3_service_governance:
    timeout_retry_circuit_breaker: "<strategy>"
    health_and_graceful_shutdown: "<check>"
    rollback_strategy: "<plan>"
  A4_observability:
    access_log: "<fields/sample>"
    operation_log_user: "<fields/sample>"
    operation_log_operator: "<fields/sample>"
    error_log: "<fields/sample>"
    debug_log: "<switch/redaction>"
    metrics_alert_slo: "<rules/thresholds>"
  A5_product_ops:
    event_collection: "<event names/fields>"
    experiment_gray: "<bucket/version>"
    feedback_loop: "<collect-evaluate-optimize-rollback>"
  A6_security_privacy:
    data_classification: "<PUBLIC/PII/SENSITIVE/SECRET>"
    masking_encryption_retention: "<policy>"
    auditability: "<traceability>"
  A7_contract_metadata_consistency:
    openapi_synced: true
    openapi_paths: []
    metadata_synced: true
    metadata_files: []
    endpoint_catalog_synced: true
  A8_test_automation:
    mock:
      app: []
      service: []
    unit:
      app: []
      service: []
    contract:
      app: []
      service: []
    integration:
      app: []
      service: []
    uat:
      cases: []
      automation: []
execution:
  local_gate: "make gate"
  full_gate: "make gate-full"
EOF
fi

if [[ ! -f "$dir/tasks.md" ]]; then
  cat >"$dir/tasks.md" <<'EOF'
# 任务拆解（端云一体）

## 云侧（quwoquan_service）
- [ ] contracts：更新 OpenAPI + contracts 文档
- [ ] specs：补齐场景与约束
- [ ] tasks：在 `quwoquan_service/tasks.md` 增加本特性任务（引用 §0 全服务统一能力）
- [ ] 实现：DDD 分层 + 复用 `runtime/*`
- [ ] 测试：单测 + 契约测 + 集成测

## 端侧（quwoquan_app）
- [ ] 页面/数据源迁移：Repository mock/remote 一键切换
- [ ] RemoteRepository：严格按 contracts 解码（items/nextCursor）
- [ ] headers：统一注入（pageId 三段式命名）
- [ ] 测试：单测/集成（必要时加 mock server）

## 门禁
- [ ] 本地：`make gate`
- [ ] CI：required checks 全绿

EOF
fi

if [[ ! -f "$dir/traceability.yaml" ]]; then
  cat >"$dir/traceability.yaml" <<'EOF'
feature:
  id: "<Fxxx>"
  name: "<feature-name>"
opsx:
  change_id: "<opsx-change-id>"
  specs:
    - "<opsx-spec-id>"
services:
  - "<service-name>"
objects:
  - "<domain-object>"
apis:
  - method: GET
    path: /v1/example/path
metadata:
  entities:
    - "<entity-name>"
  fields:
    - "<field-name>"
cross_cutting:
  observability: true
  product_ops: true
  service_governance: true
  config_governance: true
tests:
  unit:
    - "<path/to/unit_test>"
  contract:
    - "<path/to/contract_test>"
  integration:
    - "<path/to/integration_test>"
  uat:
    - "<uat-case-id>"
test_automation:
  mock:
    app:
      - "<path/to/mock_test>"
    service:
      - "<path/to/mock_or_stub_test>"
  contract:
    app:
      - "<path/to/client_contract_test>"
    service:
      - "<path/to/openapi_or_schema_contract_test>"
  integration:
    app:
      - "<path/to/app_integration_test>"
    service:
      - "<path/to/service_integration_test>"
  uat:
    cases:
      - "<uat-case-id>"
    automation:
      - "<path/to/uat_automation_script_or_plan>"
EOF
fi

echo "[new_feature_fullstack] created: $dir"
echo "[new_feature_fullstack] reminder: update changes/feature_catalog.yaml with opsx mapping and delivery_profile"

