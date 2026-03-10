# 特性目录树总揽（三层目录）

本目录采用三层治理模型：

- `L1_capability`
- `L2_feature`
- `L3_story`

其中：

- 目录层只保留到 `L3_story`
- `Task` 只存在于 `tasks.md` 或后续 `tasks.yaml`
- `tree_index.yaml` 是特性树结构唯一索引真相源

---

## 目录结构

推荐路径：

```text
specs/feature-tree/<l1-capability>/
  spec.md
  design.md
  tasks.md
  acceptance.yaml
  <l2-feature>/
    spec.md
    design.md
    tasks.md
    acceptance.yaml
    <l3-story>/
      spec.md
      design.md
      tasks.md
      acceptance.yaml
```

约束：

- 目录名使用 kebab-case
- `spec.md` / `design.md` / `tasks.md` / `acceptance.yaml` 是唯一正式治理文档
- 不允许继续创建第四层目录

---

## L1 落地范围

功能 L1（5）：

- `discovery-content`
- `circle-community`
- `chat-conversation`
- `user-identity-profile-relationship`
- `assistant-run-learning`

非功能 L1（4）：

- `runtime`
- `platform-ops-governance`
- `product-ops-growth`
- `gateway-orchestrator-foundation`

---

## 唯一真相源

- 特性树结构：`specs/feature-tree/tree_index.yaml`
- L1/L2/L3 四件套：`specs/feature-tree/<path>/`
- L1 元数据：`specs/l1_index.yaml`

以下入口不再是结构真相源：

- `changes/feature_tree.yaml`
- `runtime/tree.yaml`

---

## 开发入口

- 新增 Story：`bash scripts/new_feature_fullstack.sh <l1_capability> <l2_feature> <l3_story>`
- 重建索引：`go run ./quwoquan_service/tools/gen_tree_index specs/feature-tree specs/feature-tree/tree_index.yaml`
- 校验：`bash scripts/verify_feature_traceability.sh`、`bash scripts/verify_feature_tree_refactor.sh`

