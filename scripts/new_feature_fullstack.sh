#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

l1="${1:-}"
l2="${2:-}"
l3="${3:-}"

if [[ -z "$l1" || -z "$l2" || -z "$l3" ]]; then
  echo "usage: bash scripts/new_feature_fullstack.sh <l1_capability> <l2_feature> <l3_story>" 1>&2
  echo "example: bash scripts/new_feature_fullstack.sh runtime development-workflow-governance three-level-directory-review" 1>&2
  exit 2
fi

feature_dir="specs/feature-tree/${l1}/${l2}"
story_dir="${feature_dir}/${l3}"
mkdir -p "$feature_dir" "$story_dir"

if [[ ! -f "$feature_dir/spec.md" ]]; then
  cat >"$feature_dir/spec.md" <<EOF
# L2 Feature：${l2}

## 背景与动机

TODO

## Feature 范围

TODO

## 不做什么（Out of Scope）

TODO

## 约束

TODO
EOF
fi

if [[ ! -f "$feature_dir/design.md" ]]; then
  cat >"$feature_dir/design.md" <<EOF
# ${l2} 设计方案

## 设计动因

TODO

## Feature 聚合策略

TODO

## 关键设计决策

TODO
EOF
fi

if [[ ! -f "$feature_dir/tasks.md" ]]; then
  cat >"$feature_dir/tasks.md" <<'EOF'
# 任务列表

## 当前交付任务
- [ ] 收敛 Feature 边界与 Story 划分

## 搁置任务（带规划）
- [ ] 无

## 未来演进任务
- [ ] 无
EOF
fi

if [[ ! -f "$feature_dir/acceptance.yaml" ]]; then
  cat >"$feature_dir/acceptance.yaml" <<EOF
feature: "${l2}"
level: "L2_feature"
archived: false
execution:
  local_gate: "make gate"
  full_gate: "make gate-full"
level_acceptance:
  A1:
    criteria: "Feature 范围、边界与 Story 归属已冻结"
    status: pending
    linked_tasks: []
    test_layers:
      T1: required
      T2: optional
      T3: optional
      T4: optional
    tests: []
EOF
fi

if [[ ! -f "$story_dir/spec.md" ]]; then
  cat >"$story_dir/spec.md" <<EOF
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

if [[ ! -f "$story_dir/design.md" ]]; then
  cat >"$story_dir/design.md" <<EOF
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

if [[ ! -f "$story_dir/tasks.md" ]]; then
  cat >"$story_dir/tasks.md" <<'EOF'
# 任务列表

## 当前交付任务
- [ ] T1: TODO

## 搁置任务（带规划）
- [ ] 无

## 未来演进任务
- [ ] 无
EOF
fi

if [[ ! -f "$story_dir/acceptance.yaml" ]]; then
  cat >"$story_dir/acceptance.yaml" <<EOF
feature: "${l3}"
level: "L3_story"
archived: false
execution:
  local_gate: "make gate"
  full_gate: "make gate-full"
level_acceptance:
  A1:
    criteria: "TODO"
    status: pending
    linked_tasks: []
    test_layers:
      T1: required
      T2: optional
      T3: optional
      T4: optional
    tests: []
  A2:
    criteria: "TODO"
    status: pending
    linked_tasks: []
    test_layers:
      T1: required
      T2: required
      T3: optional
      T4: optional
    tests: []
  A3:
    criteria: "TODO"
    status: pending
    linked_tasks: []
    test_layers:
      T1: required
      T2: required
      T3: required
      T4: optional
    tests: []
EOF
fi

echo "[new_feature_fullstack] created: $story_dir"
