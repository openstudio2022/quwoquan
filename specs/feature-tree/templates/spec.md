# L1 Capability: templates

## 能力定位

`templates` 不是面向终端用户的业务能力，而是 `specs/feature-tree/` 的作者模板集合。  
它的职责是为 L2 Journey、L3 Scenario 的 `acceptance.yaml` 与 `plan.yaml` 提供统一起草骨架，保证规格树结构长期一致。

## 背景与动机

如果 feature-tree 没有统一模板，不同会话和不同作者会各写各的格式，最终导致：

1. `acceptance.yaml` 字段不一致；
2. `plan.yaml` 切片和证据口径漂移；
3. gate 难以持续做结构校验。

因此需要保留一个正式的模板节点，承载规格作者可复用的最小模板资产。

## 目标用户

- 维护 `spec.md / design.md / acceptance.yaml / plan.yaml` 的产品与研发作者。
- 需要新增 L2/L3 节点时的规格起草者。

## 功能范围

- `l2_journey_acceptance.yaml` 模板。
- `l3_scenario_acceptance.yaml` 模板。
- `plan.yaml` 模板。
- 对模板用途与边界的正式说明。

## Out of Scope

- 任何线上业务能力。
- 运行时代码、metadata、codegen 产物。
- 面向终端用户的交互设计。

## 约束

- 模板只提供结构骨架，不替代具体业务规格。
- 模板字段命名要与 gate 校验规则保持一致。
- 模板目录本身必须满足 feature-tree 节点的基础文件要求。

## 角色分工

- `templates`：维护规格模板文件。
- `feature-tree` gate：校验模板与实际节点结构的一致性。

## 数据生命周期合同

- 模板更新影响后续新建规格，但不直接改变既有业务节点语义。
- 模板是 authoring asset，不参与运行时发布。

## 非功能目标

- 模板字段稳定、易复制、易校验。
- 新作者可在单个目录内找到最小起草骨架。

## 验收重点

1. 模板目录具备完整的 `spec / design / acceptance / plan` 结构。
2. L2 与 L3 模板字段可直接被新节点复用。
3. 模板资产不会被误解为业务能力实现。
