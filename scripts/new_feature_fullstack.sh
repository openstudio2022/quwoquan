#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

l1="${1:-}"
l2="${2:-}"
l3="${3:-}"

if [[ -z "$l1" || -z "$l2" || -z "$l3" ]]; then
  echo "usage: bash scripts/new_feature_fullstack.sh <l1_capability> <l2_journey> <l3_scenario>" 1>&2
  echo "example: bash scripts/new_feature_fullstack.sh runtime development-workflow-governance journey-scenario-governance" 1>&2
  exit 2
fi

journey_dir="specs/feature-tree/${l1}/${l2}"
scenario_dir="${journey_dir}/${l3}"
mkdir -p "$journey_dir" "$scenario_dir" "specs/changelog"

if [[ ! -f "$journey_dir/spec.md" ]]; then
  cat >"$journey_dir/spec.md" <<EOF
# L2 Journey：${l2}

## 背景与动机

TODO

## Journey 范围

TODO

## 不做什么（Out of Scope）

TODO

## 约束

TODO
EOF
fi

if [[ ! -f "$journey_dir/design.md" ]]; then
  cat >"$journey_dir/design.md" <<EOF
# ${l2} 设计方案

## 设计动因

TODO

## Journey 聚合策略

TODO

## 关键设计决策

TODO
EOF
fi

if [[ ! -f "$journey_dir/plan.yaml" ]]; then
  cat >"$journey_dir/plan.yaml" <<EOF
version: 1
node: ${l1}/${l2}

derived_from:
  spec: spec.md
  design: design.md
  acceptance: acceptance.yaml
  changelog: []

slices:
  - id: P1
    title: freeze journey scope
    goal: freeze journey boundaries and scenario split
    depends_on: []
    acceptance_refs: [J1]
    planned_evidence: [T1_schema]
    done_when:
      - journey scope is frozen
    status: planned
EOF
fi

if [[ ! -f "$journey_dir/acceptance.yaml" ]]; then
  cat >"$journey_dir/acceptance.yaml" <<EOF
version: 2
feature: "${l2}"
level: "L2_journey"
archived: false
execution:
  local_gate: "make gate"
  full_gate: "make gate-full"
scope:
  summary: "TODO"
  composed_scenarios: ["${l3}"]
  out_of_scope: []
journey_acceptance:
  J1:
    title: "Journey 范围、边界与 Scenario 归属已冻结"
    journey: "TODO"
    scenario_refs: ["${l3}"]
    done_when:
      - "TODO"
    release_guardrails: []
    evidence:
      primary: [T3_cross_service_integration]
      supporting: [T1_schema]
    tests:
      planned: []
      recorded: []
    status: pending
EOF
fi

if [[ ! -f "$scenario_dir/spec.md" ]]; then
  cat >"$scenario_dir/spec.md" <<EOF
# ${l3}

## 背景与动机

TODO

## 目标用户

TODO

## 功能范围

TODO

## 不做什么（Out of Scope）

TODO

## 约束

TODO

## 对标输入与吸收结论

TODO

## 验收重点

TODO
EOF
fi

if [[ ! -f "$scenario_dir/design.md" ]]; then
  cat >"$scenario_dir/design.md" <<EOF
# ${l3} 设计方案

## 设计动因

TODO

## 上游输入评审

TODO

## 方案对比

### 方案 A
TODO

### 方案 B
TODO

## 选型决策

TODO

## 关键设计决策

TODO
EOF
fi

if [[ ! -f "$scenario_dir/plan.yaml" ]]; then
  cat >"$scenario_dir/plan.yaml" <<EOF
version: 1
node: ${l1}/${l2}/${l3}

derived_from:
  spec: spec.md
  design: design.md
  acceptance: acceptance.yaml
  changelog: []

slices:
  - id: P1
    title: implement primary scenario path
    goal: deliver the minimum scenario path
    depends_on: []
    acceptance_refs: [A1]
    planned_evidence: [T1_schema, T2_app_mock]
    done_when:
      - primary scenario path works
    status: planned
EOF
fi

if [[ ! -f "$scenario_dir/acceptance.yaml" ]]; then
  cat >"$scenario_dir/acceptance.yaml" <<EOF
version: 2
feature: "${l3}"
level: "L3_scenario"
archived: false
execution:
  local_gate: "make gate"
  full_gate: "make gate-full"
scope:
  summary: "TODO"
  journey_bindings: [J1]
  in_scope: []
  out_of_scope: []
scenario_acceptance:
  A1:
    title: "Primary scenario"
    scenario: "TODO"
    journey_step: "TODO"
    done_when:
      - "TODO"
    edge_cases: []
    status: pending
    linked_plan_items: [P1]
    evidence:
      primary: [T1_schema, T2_app_mock]
      supporting: [T3_app_api_integration]
    tests:
      planned: []
      recorded: []
  A2:
    title: "Fallback or boundary"
    scenario: "TODO"
    journey_step: "TODO"
    done_when:
      - "TODO"
    edge_cases: []
    status: pending
    linked_plan_items: []
    evidence:
      primary: [T2_app_mock]
      supporting: [T1_schema]
    tests:
      planned: []
      recorded: []
EOF
fi

echo "[new_feature_fullstack] created: $scenario_dir"
echo "[new_feature_fullstack] next: create or update specs/changelog/CR-YYYYMMDD-NNN-<slug>.yaml"
