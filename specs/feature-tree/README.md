# 特性目录树总揽

本目录是整个应用的产品规格、知识、设计和测试底座。

正式模型为：

- 应用根：全局产品定位、Journey/Scenario、UAT、全局架构与治理。
- `L1_domain_service`：产品领域服务边界。
- `L2_business_capability`：领域内业务能力。
- `L3_story`：最小可闭环价值点。

---

## 目录结构

```text
specs/feature-tree/
  spec.md
  design.md
  acceptance.yaml
  journey_scenario_registry.yaml
  tree_index.yaml

  <domain-service>/
    spec.md
    design.md
    acceptance.yaml

    <business-capability>/
      spec.md
      design.md
      acceptance.yaml

      <story>/
        spec.md
        acceptance.yaml
```

约束：

- 目录名使用 kebab-case。
- Story 层不设 `design.md`。
- 特性树内不再新增 `树内计划文档` 或 `树内任务文档`。
- Journey / Scenario 不作为目录层，只通过应用根 registry 和根层文档表达。
- 增量变更统一写入 `specs/changelog/CR-*.yaml`。

---

## 文档分工

| 文档 | 适用层级 | 职责 |
|---|---|---|
| `spec.md` | 应用根、领域服务、业务能力、Story | 定位、范围、边界、术语、规则、Out of Scope |
| `design.md` | 应用根、领域服务、业务能力 | 架构、职责边界、依赖交互、技术约束、观测和演进 |
| `acceptance.yaml` | 应用根、领域服务、业务能力、Story | UAT/SIT/GWT/contract、done_when、证据和测试 |
| `journey_scenario_registry.yaml` | 应用根 | 跨领域 Journey/Scenario 与目录节点映射 |
| `tree_index.yaml` | 应用根 | 特性树结构索引 |

---

## 唯一真相源

- 特性树结构：`specs/feature-tree/tree_index.yaml`。
- 跨领域 Journey / Scenario：`specs/feature-tree/journey_scenario_registry.yaml`。
- 领域工程映射：`specs/l1_index.yaml`。
- 增量变更：`specs/changelog/CR-*.yaml`。
- metadata 契约：`quwoquan_service/contracts/metadata/**`。

---

## 当前领域服务

当前领域服务以 `tree_index.yaml` 和 `specs/l1_index.yaml` 为准。存量节点仍可能保留旧 `L1_domain_service / L2_business_capability / L2_business_capability / L3_story / L3_story` 字段；新增节点必须使用：

- `L1_domain_service`
- `L2_business_capability`
- `L3_story`

---

## 开发入口

- 新增节点：使用新脚手架创建 `domain-service / business-capability / story`。
- 重建索引：`go run ./quwoquan_service/tools/gen_tree_index specs/feature-tree specs/feature-tree/tree_index.yaml`（生成器迁移前，禁止手动把旧层级作为新增节点标准）。
- 校验：`bash quwoquan_ops/gate/scaffold/verify_feature_tree_refactor.sh`、`bash quwoquan_ops/gate/scaffold/verify_acceptance_standard.sh`。

---

## 迁移完成态

应用根三件套、registry、模板、脚手架和 gate 已统一为三层模型。正式特性树不再保留
`树内任务文档`、`树内计划文档`、Story 设计文档或旧 acceptance schema。
