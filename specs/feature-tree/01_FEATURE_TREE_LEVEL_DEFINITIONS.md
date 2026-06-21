# 特性树层级定义与分解规范

> **权威**：本文定义仓库特性树唯一正式目录层级。测试工程层只使用 `local_contract`、`api_integration`、`user_acceptance`；Journey / Scenario 只在应用根编排，不作为目录层。

---

## 一、核心原则

### 1.1 应用根 + 三层目录

| 层级 | 语义 | 是否目录层 | 是否设计层 | 是否验收主层 |
|---|---|---|---|---|
| 应用根 | 全 App 产品定位、全局架构、跨领域 Journey/Scenario、UAT | 根上下文 | 是 | 是 |
| `L1_domain_service` | 产品领域服务边界与服务治理 | 是 | 是 | 是 |
| `L2_business_capability` | 领域内稳定业务能力与能力级 SIT | 是 | 是 | 是 |
| `L3_story` | 最小可闭环价值点、GWT、接口契约 | 是 | 否 | 是 |

### 1.2 非目录对象

- `Journey`：端到端用户旅程，写在应用根 `spec.md` 与 `journey_scenario_registry.yaml`。
- `Scenario`：Journey 下的可验收跨领域场景，写在应用根 `acceptance.yaml` 与 registry。
- `plan`：执行层临时计划，不落为特性树正式节点文档。
- 会话 todo：当前 AI 会话或 PR 的临时执行清单，不写回特性树。

### 1.3 总体原则

- 树层级只表达交付对象和责任归属。
- 验收层级表达 UAT / SIT / GWT / contract。
- 测试工程层只表达验证方式：`local_contract`、`api_integration`、`user_acceptance`。
- 技术切面（schema、policy、guard、report、model）应写入对应层级文档，不再新增目录层。

---

## 二、层级定义

### 2.1 应用根

| 属性 | 定义 |
|---|---|
| 位置 | `specs/feature-tree/` |
| 文档 | `spec.md`、`design.md`、`acceptance.yaml`、`journey_scenario_registry.yaml`、`tree_index.yaml` |
| 作用 | 定义整个应用的产品规格、知识、全局设计、跨领域旅程、UAT 与发布治理 |

应用根必须回答：

- 全 App 的用户价值、产品边界、全局术语是什么。
- 关键 Journey / Scenario 如何跨领域服务组合。
- 全局端云分层、领域边界、技术约束和治理规则是什么。
- UAT、SLO/KPI、灰度、回滚、观测如何验收。

### 2.2 `L1_domain_service`

| 属性 | 定义 |
|---|---|
| 语义 | 产品领域服务边界，不等同于单个后端部署进程 |
| 目录 | `specs/feature-tree/<domain-service>/` |
| 文档 | `spec.md`、`design.md`、`acceptance.yaml` |
| 作用 | 定义领域服务定位、能力范围、边界、周边依赖、服务治理和运行约束 |

判断标准：

- 是否代表长期稳定的产品领域或平台领域。
- 是否能映射到 app UI、metadata、service/deploy、test 的一组工程资产。
- 是否有清晰的上下游依赖和领域对象边界。

### 2.3 `L2_business_capability`

| 属性 | 定义 |
|---|---|
| 语义 | 领域内稳定业务能力 |
| 目录 | `specs/feature-tree/<domain-service>/<business-capability>/` |
| 文档 | `spec.md`、`design.md`、`acceptance.yaml` |
| 作用 | 定义能力范围、状态机、策略、跨 Story 编排、SIT 与能力级测试证据 |

判断标准：

- 是否是一组 Story 的稳定业务容器。
- 是否需要能力级设计来说明状态、策略、数据流或端云交互。
- 是否能用 SIT 验证多个 Story 组合后的业务流。

### 2.4 `L3_story`

| 属性 | 定义 |
|---|---|
| 语义 | 最小独立闭环的价值点 |
| 目录 | `specs/feature-tree/<domain-service>/<business-capability>/<story>/` |
| 文档 | `spec.md`、`acceptance.yaml` |
| 作用 | 定义单个价值点的行为边界、GWT、接口契约、done_when 和最小测试证据 |

判断标准：

- 是否能独立判断 done / not done。
- 是否能写出明确 GWT。
- 是否能映射到一个或少量接口契约、模块交互或 UI 行为。
- 是否不需要独立架构设计；需要设计时应上收到业务能力层。

---

## 三、分解决策树

```text
用户需求 / 产品问题
  │
  ▼
是否影响跨领域用户路径？
  ├─ 是 → 更新应用根 Journey / Scenario registry 与 UAT
  └─ 否 → 进入领域归属判断
        │
        ▼
是否属于既有产品领域服务？
  ├─ 否 → 新建或调整 L1_domain_service
  └─ 是 → 归入既有 L1_domain_service
        │
        ▼
是否是一组稳定 Story 的业务能力？
  ├─ 是 → 新建或归入 L2_business_capability
  └─ 否 → 归入最接近的既有业务能力
        │
        ▼
是否能独立闭环为最小价值点？
  ├─ 是 → 新建或更新 L3_story
  └─ 否 → 写入现有 Story 的 spec/acceptance 或会话 todo
```

---

## 四、验收映射

| 来源 | 落点 | 验收语言 | 测试证据 |
|---|---|---|---|
| 用户需求 | 应用根 Journey / Scenario | UAT | `user_acceptance`，辅以 `api_integration` |
| 领域边界与治理 | `L1_domain_service` | 领域服务验收 | `api_integration/local_contract`，必要时 `user_acceptance` |
| 能力组合 | `L2_business_capability` | SIT | `api_integration`，辅以 `local_contract` |
| 最小价值点 | `L3_story` | GWT + contract | `local_contract`，必要时 `api_integration/user_acceptance` |

---

## 五、实施卡点映射

| 阶段 | 作用对象 |
|---|---|
| `/explore` | 确认应用根 Journey/Scenario、`L1_domain_service`、`L2_business_capability`、目标 `L3_story` |
| `/prd` | 创建或更新 `spec.md` 与 `acceptance.yaml`，必要时更新应用根 registry 与 CR |
| `/design` | 只更新应用根、领域服务、业务能力三层 `design.md`；Story 不产生 `design.md` |
| `/dev` | 从 Story `acceptance.yaml`、变更范围和会话 todo 派生执行动作 |
| `/verify` | 验证 Story、业务能力 SIT、受影响 UAT 和三层测试证据 |
| `/commit` | 提交已完成 Story、相关能力/领域文档和 CR 范围 |

---

## 六、违规规则

以下情况一律视为违规：

- 新增四层以上特性树目录。
- 将 Journey / Scenario 建成目录层。
- 新增树内 `树内计划文档`、`树内任务文档` 或 Story 设计文档 作为正式治理文档。
- 将测试层写成 `L3/L4`。
- 在 Story 中维护跨 Story 架构设计。
- 新增节点未能映射到 `specs/l1_index.yaml` 的工程资产。

---

## 七、总结

仓库特性树唯一正式结构为：

```text
AppRoot
  └── L1_domain_service
        └── L2_business_capability
              └── L3_story
```

应用根负责产品与跨领域编排，领域服务负责边界，业务能力负责组合设计和 SIT，Story 负责最小价值点、GWT 和接口契约。
