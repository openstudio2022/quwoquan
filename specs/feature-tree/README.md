# 特性目录树总揽（Journey / Scenario）

本目录采用三层治理模型：

- `L1_capability`
- `L2_journey`
- `L3_scenario`

其中：

- 目录层只保留到 `L3_scenario`
- 节点正式文档为 `spec.md / design.md / plan.yaml / acceptance.yaml`
- 会话级 todo 不落盘到特性树
- `tree_index.yaml` 是特性树结构唯一索引真相源
- 增量变更统一写入 `specs/changelog/`

---

## 目录结构

推荐路径：

```text
specs/feature-tree/<l1-capability>/
  spec.md
  design.md
  plan.yaml
  acceptance.yaml
  <l2-journey>/
    spec.md
    design.md
    plan.yaml
    acceptance.yaml
    <l3-scenario>/
      spec.md
      design.md
      plan.yaml
      acceptance.yaml
```

约束：

- 目录名使用 kebab-case
- `spec.md` / `design.md` / `plan.yaml` / `acceptance.yaml` 是唯一正式节点治理文档
- 不允许继续创建第四层目录
- 模板见 `specs/feature-tree/templates/`
- 迁移指导见 `specs/feature-tree/02_JOURNEY_SCENARIO_MIGRATION_GUIDE.md`
- 样板见 `specs/feature-tree/03_PROFILE_HOMEPAGE_REDESIGN_MIGRATION_SAMPLE.md`

---

## L1 落地范围

当前 L1（以 `tree_index.yaml` 为准）：

- `discovery-content`
- `circle-community`
- `chat-conversation`
- `user-identity-profile-relationship`
- `assistant-run-learning`
- `global-search-experience`
- `shared-homepage-network`
- `runtime`
- `platform-ops-governance`
- `product-ops-growth`
- `gateway-orchestrator-foundation`
- `recommendation-platform`

---

## 唯一真相源

- 特性树结构：`specs/feature-tree/tree_index.yaml`
- L1/L2/L3 四件套：`specs/feature-tree/<path>/`
- 增量变更：`specs/changelog/CR-*.yaml`
- L1 元数据：`specs/l1_index.yaml`

以下入口不再是结构真相源：

- `changes/feature_tree.yaml`
- `runtime/tree.yaml`

---

## 开发入口

- 新增 Scenario：`bash scripts/new_feature_fullstack.sh <l1_capability> <l2_journey> <l3_scenario>`
- 重建索引：`go run ./quwoquan_service/tools/gen_tree_index specs/feature-tree specs/feature-tree/tree_index.yaml`
- 校验：`bash scripts/verify_feature_traceability.sh`、`bash scripts/verify_feature_tree_refactor.sh`

