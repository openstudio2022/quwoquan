# 特性树文档标准（应用根 / 领域服务 / 业务能力 / Story 版）

> **权威**：特性树是整个应用的产品规格、知识、设计与测试底座。正式目录层只表达交付责任归属，不表达测试层，也不把 Journey / Scenario 建成目录层。

---

## 一、正式结构

正式结构为“应用根 + 三层目录”：

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

正式目录层级：

| 层级 | 语义 | 目录层 | 设计文档 |
|---|---|---|---|
| 应用根 | 全 App 定位、跨领域 Journey/Scenario、UAT、全局治理 | 否，根上下文 | 是 |
| `L1_domain_service` | 产品领域服务边界，不等同于单个后端部署进程 | 是 | 是 |
| `L2_business_capability` | 领域内稳定业务能力与 SIT 收口 | 是 | 是 |
| `L3_story` | 最小可闭环价值点、GWT 与接口契约收口 | 是 | 否 |

`树内计划文档` 不再是特性树正式节点文档。开发计划只存在于当前会话计划、PR 拆分或外部执行台账中，不能作为规格、设计或验收的第二真相源。

---

## 二、Journey / Scenario 的位置

`Journey` 与 `Scenario` 是应用根编排对象，不是目录层。

- `Journey`：用户从目标到结果的端到端路径，通常跨多个领域服务和业务能力。
- `Scenario`：Journey 下可被 UAT 验证的跨领域场景组合。
- `journey_scenario_registry.yaml`：记录 Journey / Scenario、UAT、关联领域服务、业务能力、Story 与边界。

禁止：

- 把 Journey / Scenario 建成 `L2` / `L3` 目录层。
- 通过第四层目录表达 `subfeature/detail/leaf`。
- 在领域服务目录中维护另一套跨领域 Journey 索引。

---

## 三、Spec / Design / Acceptance 分工

三类正式文档分工固定。

| 文档 | 回答的问题 | 不负责 |
|---|---|---|
| `spec.md` | 为什么做、做什么、不做什么、用户或业务边界是什么 | 技术方案和测试执行细节 |
| `design.md` | 如何组织系统长期承载这些规格 | 需求清单、验收用例、开发任务 |
| `acceptance.yaml` | 如何判定完成，证据是什么 | 架构设计和实现计划 |

### `spec.md`

必须包含：

- 层级与定位。
- 背景、目标用户或平台价值。
- 范围、Out of Scope、术语和业务对象。
- 关键业务规则、边界、依赖和验收关注点。
- 涉及用户旅程时，引用应用根 Journey / Scenario。

### `design.md`

只存在于应用根、领域服务和业务能力层。

- 应用根 `design.md`：描述全局架构、端云分层、领域边界、跨领域编排、全局技术约束、数据生命周期、观测、灰度和回滚。
- 领域服务 `design.md`：描述领域能力范围、上下游依赖、领域对象、接口协作、数据归属、服务架构、技术约束、SLO、观测和运行治理。
- 业务能力 `design.md`：描述能力内部的关键协作、状态机、策略、数据流、端云交互和测试切面。
- Story 不设 `design.md`；Story 的实现约束、接口契约和行为规则写入 `spec.md` 与 `acceptance.yaml`，设计决策上收到业务能力层。

### `acceptance.yaml`

必须表达：

- 层级、范围、状态和执行门禁。
- UAT / SIT / GWT / contract 的验收意图。
- `done_when`、边界条件、证据层与测试文件或命令。
- 统一测试证据层：`T1`、`T2`、`T3`、`T4`。

---

## 四、验收层级

| 层级 | 验收主语 | 验收标准 | 主要证据 |
|---|---|---|---|
| 应用根 | 用户需求与完整 Journey | UAT | `T4`，辅以 `T3`、SLO/KPI、灰度和回滚 |
| `L1_domain_service` | 领域边界与服务治理 | 领域服务验收 | `T1/T3`，必要时 `T4` |
| `L2_business_capability` | 能力内多 Story 组合 | SIT | `T2/T3` |
| `L3_story` | 最小价值点 | GWT + 接口契约 | `T1/T2`，涉及远端边界时补 `T3` |

测试层只表达验证方式，不表达特性树层级：

- `T1`：契约与静态校验。
- `T2`：模块与交互验证。
- `T3`：端云集成验证。
- `T4`：端到端旅程验证。

---

## 五、索引与映射

唯一真相源：

- 特性树结构：`specs/feature-tree/tree_index.yaml`。
- Journey / Scenario 编排：`specs/feature-tree/journey_scenario_registry.yaml`。
- 领域服务工程映射：`specs/l1_index.yaml`。
- 增量变更：`specs/changelog/CR-*.yaml`。
- 契约、字段、错误码、路径、operation、surface、route：`quwoquan_service/contracts/metadata/**`。

`specs/l1_index.yaml` 必须把产品领域服务映射到：

- App UI 模块。
- App cloud repository / generated runtime。
- Metadata domain / aggregate。
- Service 目录和 deploy 进程。
- 测试目录与门禁入口。

---

## 六、禁止项

以下行为视为违规：

- 新增四层以上特性树目录。
- 新增树内 `树内计划文档`、`树内任务文档` 或 Story 设计文档 作为正式治理文档。
- 在 Story 层维护架构设计和跨 Story 设计决策。
- 在 acceptance 中使用 `L3/L4` 指代测试层。
- 让 `specs/changelog/` 复刻一套特性树层级。
- 在脚手架、命令文案、gate 中继续把 Journey / Scenario 当目录层。

---

## 七、迁移策略

本标准先约束新增节点和新模板。存量节点按批迁移：

1. 先落应用根三件套与 `journey_scenario_registry.yaml`。
2. 再切换模板、脚手架和 gate。
3. 新增节点强制采用新模型。
4. 存量节点保留兼容，但不得继续扩展旧 `树内计划文档`、`树内任务文档`、Story 设计文档。
5. 试点验证通过后，分批删除旧 schema 与旧模板。

---

## 八、总结

特性树的正式治理语言为：

```text
应用根：spec.md / design.md / acceptance.yaml / journey_scenario_registry.yaml
L1_domain_service：spec.md / design.md / acceptance.yaml
L2_business_capability：spec.md / design.md / acceptance.yaml
L3_story：spec.md / acceptance.yaml
```

用户 Journey / Scenario 在应用根编排，领域服务 / 业务能力 / Story 在目录树中承载责任归属、规格与验收。
