# 特性树层级定义与分解规范（Journey / Scenario 版）

> **权威**：本文档定义仓库唯一正式层级。
>
> - `L1_capability`
> - `L2_journey`
> - `L3_scenario`
>
> `plan slice` 与会话 todo 继续存在，但都不属于目录层级。

---

## 一、核心原则

### 1.1 三层目录模型

| 层级 | 语义 | 是否目录层 | 是否验收主层 |
|------|------|------------|--------------|
| `L1_capability` | 业务能力 / 平台能力 | 是 | 是 |
| `L2_journey` | 端到端用户旅程与组合验收容器 | 是 | 是 |
| `L3_scenario` | 单环节场景与最小实施单元 | 是 | 是 |

### 1.2 Plan 与 todo 的位置

- `plan slice` 是稳定实施切片
- `plan slice` 只存在于 `plan.yaml`
- 会话 todo 只存在于 AI 会话上下文
- 两者都不再占用目录层

### 1.3 总体原则

- 树层级只表达交付对象，不表达测试层。
- `L2_journey` 只表达稳定用户旅程、跨场景组合规则与发布收口。
- `L3_scenario` 只表达单环节场景、异常边界与最小实施单元。
- `contract / policy / schema / model / guard / report` 这类技术切面应回收到节点文档或 CR 中，而不是再占目录层。

---

## 二、层级详细定义

### 2.1 `L1_capability`

| 属性 | 定义 |
|------|------|
| 语义 | 长期存在的业务能力或平台能力边界 |
| 目录 | `specs/feature-tree/<l1-name>/` |
| 作用 | 承载能力边界、关键旅程、NFR、发布治理，以及其下 Journey 组织 |

### 2.2 `L2_journey`

| 属性 | 定义 |
|------|------|
| 语义 | 稳定的端到端用户旅程，负责把一组相关 Scenario 聚合在一起 |
| 目录 | `specs/feature-tree/<L1>/<l2-journey>/` |
| 作用 | 承载旅程范围、边界、聚合规则、Journey 级设计与组合验收 |

**判断标准**：

- 是否是一条长期稳定、可承载多个 Scenario 的用户旅程？
- 是否主要关心组合体验、发布 guardrails、跨场景一致性？
- 是否更像“旅程容器”，而不是某一个环节实现？

**禁止**：

- 用 `L2_journey` 表示单次开发任务
- 在 `L2_journey` 下继续建 `subfeature/detail/leaf`
- 在 `L2_journey` 中写具体文件级实施清单

### 2.3 `L3_scenario`

| 属性 | 定义 |
|------|------|
| 语义 | 最小独立实施、独立验收、独立测试映射的场景 |
| 目录 | `specs/feature-tree/<L1>/<L2>/<l3-scenario>/` |
| 作用 | 承载场景目标、异常边界、实施计划、验收和测试证据的主单元 |

**判断标准**：

- 是否对应 Journey 中一个明确步骤或环节？
- 是否可单独写 `scenario_acceptance`？
- 是否可单独判断 done / not done？
- 是否应作为 `/design`、`/dev`、`/verify`、`/commit` 的核心对象？

### 2.4 `plan slice`

| 属性 | 定义 |
|------|------|
| 语义 | 稳定的实施切片 |
| 位置 | `plan.yaml` |
| 作用 | 表达依赖顺序、验收回链、退出条件与预期证据 |

### 2.5 `session todo`

| 属性 | 定义 |
|------|------|
| 语义 | 当前会话的临时执行清单 |
| 位置 | AI 会话上下文 |
| 作用 | 将 `plan slice` 派生为本轮可执行动作 |

---

## 三、目录与文档结构

```text
specs/feature-tree/
  <l1-capability>/
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

specs/changelog/
  CR-YYYYMMDD-NNN-slug.yaml
```

---

## 四、分解决策树

```text
需求/问题
   │
   ▼
是否属于既有能力域？
   ├─ 否 → 归属一个 L1_capability
   └─ 是
        │
        ▼
是否是一条长期稳定、可承载多个场景的用户旅程？
   ├─ 是 → 建立/归入 L2_journey
   └─ 否 → 归入既有 L2_journey
        │
        ▼
是否可形成独立实施、独立验收、独立测试映射的单环节场景？
   ├─ 是 → 建立/归入 L3_scenario
   └─ 否 → 写入该 Scenario 的文档内部、plan slice 或 CR
```

---

## 五、与验收和测试的关系

- 树层级与测试层级彻底解耦。
- 测试统一使用 `T1~T4`。
- `L1_capability`、`L2_journey`、`L3_scenario` 都可拥有 `acceptance.yaml`。
- `L2_journey` 主要聚合 `T3/T4` 证据。
- `L3_scenario` 主要收口 `T1/T2`，必要时补 `T3`。
- `plan slice` 只通过 `acceptance_ref` 回链到所属 Journey / Scenario 的验收项。

---

## 六、门禁与违规规则

以下情况一律视为违规：

- 新增 `subfeature/detail/leaf` 一类额外目录层
- 新建四层以上特性目录
- 将会话 todo 建成目录层或正式文档
- 在文档、脚本、索引中继续维护旧层级兼容表
- 继续使用 `tasks.md` 作为正式计划文档

门禁策略：

- 发现旧层级枚举：**FAIL**
- 发现四层以上目录：**FAIL**
- 发现 `acceptance.yaml` 使用旧 `level`：**FAIL**
- 发现脚手架仍产出旧层级或 `tasks.md`：**FAIL**

---

## 七、实施卡点映射

| 阶段 | 作用对象 |
|------|----------|
| `/explore` | 确认 `L1_capability`、`L2_journey` 与目标 `L3_scenario` |
| `/prd` | 创建或更新 Journey / Scenario 的 `spec.md + acceptance.yaml`，并建立 CR |
| `/design` | 完成 Journey / Scenario 的 `design.md + plan.yaml` |
| `/dev` | 读取 `plan.yaml`，派生会话 todo 并执行 |
| `/verify` | 验证 `L3_scenario` 完成度、`L2_journey` 受影响验收与测试证据 |
| `/commit` | 提交已完成的 slice 与对应 CR 范围 |

---

## 八、总结

仓库特性树的唯一正式结构为：

```text
L1_capability
  └── L2_journey
        └── L3_scenario
              └── plan slice（写在 plan.yaml）
```

会话 todo 是执行层，不再是目录层。  
增量变更通过 `specs/changelog/CR-*.yaml` 独立表达，不嵌入节点目录。
