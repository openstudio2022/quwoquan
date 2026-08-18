---
name: design
description: Record the architecture decisions (DEC) needed to satisfy a frozen spec - object boundary, command/query split, testability of each decision, failure recovery with SLO and rollback. Use when the user says 设计方案, 梳理架构, 明确边界, 明确回滚, or 明确观测.
metadata:
  kind: workflow
  command: /design
---

# design

记录满足已冻结规格所需的**当前有效**架构决定。五段执行契约见根 `AGENTS.md`。

设计只作用于 AppRoot、L1 和达到门槛的 L2。**L3 不创建 `design.md`。**
L2 只有在跨域或跨服务、外部依赖、状态或所有权变化、迁移、非平凡质量权衡、
多方案并存、特有 rollout/rollback 时才创建 design；否则指向父 L1 的 `DEC-###`。

## 触发

- 显式命令 `/design`。
- 自然语言：设计方案、梳理架构、明确边界、明确回滚、明确观测，且规格已冻结。

## 输入

- `prd` 的 HANDOFF：规格已冻结，验收锚点可测试绑定，且判定达到设计门槛。
- canonical metadata 与父层 design。

## 角色

主会话扮演 **decision-recorder**：只记录当前有效决定；架构判断由内置评审的
architect / infra-capacity / ops 角色校验，不自评。

## 执行

自由度：中（DEC 结构固定，方案裁决自由）。

1. 读最小规格父链与 canonical metadata。
2. 写清背景与非目标、所有权、协作与数据流、DEC、失败恢复、特有质量与观测、当前迁移回滚。
3. schema/DTO/path/error 文本**只引用 metadata，不复制**；类与文件清单回到代码。
4. Story 发现设计缺口时上收到 L2/L1 DEC，并让 Story spec 指向该 DEC。
5. 删除已失效设计。[MUST NOT] 保留 decision log、revision、兼容方案或历史记录。

DEC 定稿前四问：

- **领域模型** — 涉及新对象或新成员时，`owned_entity` vs `separate_aggregate`
  边界裁决与写 owner 唯一性进入 DEC（对象边界五问见
  [dev/references/object-extension.md](../dev/references/object-extension.md)）。**无界集合禁止内嵌。**
- **读写分离** — command/query facet 分流在设计期定案：command 绑定 aggregate owner
  与不变量事务，query 绑定业务命名 Reader 与 typed Slice。
  [MUST NOT] 留给实现按 URL、DTO 或存储类型去猜。
- **可测试性** — 每个 DEC 声明其行为如何被三层测试观察（导出面、对象级 typed port、
  provider-state）。**只能靠未导出符号或旁路才能验证的决策视为设计缺口，先改设计。**
- **运维运营** — 失败恢复、SLI/SLO、指标与告警、配置来源、灰度与回滚是必答项；
  环境证据入口统一 `stackctl`（见 [environment-ops](../environment-ops/SKILL.md)）。

## 交付件

**DEC 集**：`DEC-###` 编号、受影响 metadata 路径、可测试观察面、`design.md` 变更。

送审前自检：

- 不复述 spec、schema 或文件清单；
- 每个 DEC 有可测试观察面；
- 失败恢复、SLO、灰度与回滚已答或已挂 OPEN。

## 内置评审

- POST：调 `review`（workflow=`design`，segment=POST，deliverable=`dec`），
  典型角色 architect + test + ops + infra-capacity（按 profile 追加 growth / observability），
  gate 为 `make verify-feature-tree`。

## 失败与停止

- 为 L3 建 design、复述规格、绕过 metadata、缺 owner/一致性/失败恢复、
  决策不可测试观察：`GATE_BLOCK`。
- 简单需求不得强制进入本工作流。

## HANDOFF

- **产出物**：DEC 集。
- **未决项去向**：未定案的方案分叉转 `OPEN-###` 或明确 Out of Scope。
- **唯一合法下游**：`dev`；其 PRE 需要本工作流的对象边界裁决结论与 command/query 分流结论。
- **证据链**：`make verify-feature-tree` 输出。
