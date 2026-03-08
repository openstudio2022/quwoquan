---
name: /deliver
id: deliver
category: Workflow
description: 端到端交付（Design 就绪后，验收驱动完成开发，自动归档并提交入库）
---

> SDD 主流程：explore → prd → design → **deliver**（= dev + commit）→ deploy

在 `/design` 完成后，**以 acceptance.yaml A1~An 验收标准为驱动**，迭代完成开发，直至全部验收满足，再自动完成四层自验证、归档与代码提交入库。适用于「一气呵成交付到合入」的场景。

**端到端链路**：design 就绪 → **deliver 入库（L1/L2 自测通过）** → **/deploy 集成验证（L3/L4）** → 灰度到生产。

---

## 阶段准入自检（Deliver Gate）

进入本阶段前，AI Agent **必须自检**以下问题。任何未通过 → 输出 `GATE_BLOCK`。

| # | 自检问题 | 通过条件 |
|---|---------|---------|
| DL1 | spec.md + acceptance.yaml + design.md + tasks.md 是否均已写入？ | 目标节点四类文档齐全 |
| DL2 | codegen 是否已通过？ | make verify-metadata + codegen + codegen-app 均通过 |
| DL3 | 是否有未解决的 BLOCKING 依赖（其他团队/服务）？ | 无阻塞依赖，或已有明确 workaround |
| DL4 | 是否评估了实施风险和回滚方案？ | 对于涉及存储/API 的变更，有回滚预案 |
| DL5 | 本地构建环境是否就绪？ | make build 通过，数据库（MongoDB/Postgres）可用 |
| DL6 | 是否已完成 `A1~An ↔ T1~T4` 测试证据矩阵？ | 交付时不会出现“功能好了但无证据” |
| DL7 | 若涉实时性/弱网/并发，是否已定义 NFR 与灰度卡点？ | 发布风险可控 |
| DL8 | 若涉 operation / surface / route，是否已明确 metadata 唯一源并完成 codegen 基线？ | 交付阶段不再接受代码维护 override 表 |

**任一未通过 → 输出 GATE_BLOCK，停止执行。**

---

## 前置条件检查

与 `/dev` 相同：

| # | 检查项 | 判定方式 |
|---|--------|----------|
| 1 | 目标特性已创建 | 目标节点目录存在，且包含 spec.md、design.md、tasks.md、acceptance.yaml |
| 2 | G1 已通过 | 曾有 `/design` 完成，且 make verify + codegen 已通过 |
| 3 | tasks.md 已就绪 | tasks.md 中有可执行任务列表，顺序为 metadata → codegen → 测试先行 → 业务逻辑 → 重构 |
| 4 | 节点层级符合规范 | 目标节点层级符合 `01_FEATURE_TREE_LEVEL_DEFINITIONS.md` |

**若不满足**：输出补全列表，引导先执行 `/prd` + `/design`，再执行 `/deliver`。

---

## 执行流程

### 阶段 1：验收驱动的迭代开发（Dev 循环）

以 **acceptance.yaml A1~An** 为北极星，不断驱动完成未满足的验收项，直至全部满足。默认执行 **ATDD + TDD**：先验收、先失败测试、再实现、再重构。

#### 1.1 加载验收标准与 tasks

1. 读取 `acceptance.yaml`，解析 A1~An 及各验收项的含义与判定方式
2. 读取 `tasks.md`，加载当前交付任务列表
3. 建立「验收项 ↔ Story ↔ 任务/实现 ↔ 测试层(T1~T4) ↔ 发布约束」的映射

#### 1.2 验收驱动循环

```
循环：
  1) 对照 acceptance.yaml A1~An，逐项检查当前实现是否满足
  2) 若全部满足 → 退出循环，进入阶段 2
  3) 若存在未满足项 → 识别对应的 Story、tasks 或实现缺口
  4) 选取下一未完成任务或缺口，执行实现（metadata → codegen → 测试先行 → 业务逻辑 → 重构）
  5) 每完成一个 task 或缺口，立即执行 G2：
       make build
       make test-contract
       （端侧变更追加）flutter test test/cloud/ test/components/ test/ui/
  6) 更新 tasks.md 完成标记
  7) 回到步骤 1
```

**约束**（与 `/dev` 相同）：DDD 分层、metadata-first、runtime 统一、codegen 保护、Dart 设计系统、Feature 隔离、错误码规范、**PA 引擎契约规范**（引擎逻辑禁止字段名字符串字面量；活跃 contractVersion ≤2；修改契约字段走 `/extend pa-contract`，见 `02-dart-coding §5`）。若交付含 Repository / Router / Telemetry 标识迁移，必须消费 metadata 生成的 operation / surface / route 常量，禁止手写业务路径或 pageId。

**交付视图要求**：
- `acceptance.yaml` 中每条核心验收项都应有 `T1~T4` 映射
- `tasks.md` 作为 Story 的工程执行清单
- 归档前必须能说明每个 Story 的测试证据归属
- 若为实时性/弱网/并发/高增长特性，归档前必须能说明 NFR 证据、观测指标与灰度/回滚策略归属

#### 1.3 循环退出条件

- 所有 A1~An 验收项均已满足
- tasks.md 当前交付任务均已标记完成
- 核心非功能验收、灰度参数、回滚条件均已补齐

---

### 阶段 2：验证（G3）+ 自动归档

开发完成后，AI Agent **必须自动执行**：

```bash
make gate-full
```

**失败** → 输出错误 + 修复建议 → 修复后重跑 gate-full → 通过后自动归档并进入阶段 3。

---

### 阶段 3：提交入库（G4）

G3 通过后，先自动完成归档，再执行 `/commit` 的提交逻辑：

**3a. 更新 `acceptance.yaml` 顶层**：

```yaml
archived: true
archived_at: <ISO8601 当前时间>
```

**3b. 更新 `specs/feature-tree/tree_index.yaml`**：

```yaml
status: completed
```

**3c. 归档前置检查**：
- tasks.md 当前交付任务全部 `[x]`
- acceptance.yaml 若有 `level_acceptance`，所有 A1~An 的 status 为 implemented/waived/deferred

---

1. 获取 `git status`、当前分支 `CURRENT_BRANCH`，分析变更范围
2. **执行 L1+L2 门禁**（`make gate`）并通过
3. 按范围执行审计（端侧 / 云侧 / 特性树）
4. 审计通过后提交并推送，按分支开发模式合入主干（详见 `/commit`）

---

## 输出摘要

```
交付完成：<feature-name>

| 阶段           | 状态                        |
|----------------|---------------------------|
| 1. 验收驱动开发 | A1~An 满足，tasks 完成      |
| 2. 验证 (G3)   | make gate-full 通过         |
| 3. 自动归档    | 已标记 archived             |
| 4. 提交入库 (G4)| 已 commit + push           |

变更摘要：<git diff --stat>

测试与发布证据：
- T1~T4：<证据概览>
- NFR：<实时性/弱网/并发/弹性/体验结论>
- 灰度：<步进/SLO/回滚条件>

后续：执行 /deploy 完成 integration 部署、L3/L4 验证、灰度到 prod。
```

---

## 与其他命令的关系

| 命令 | 作用 | 与 /deliver 关系 |
|------|------|----------------|
| `/dev` | 逐 task 实施，每 task 后 G2 | deliver 的阶段 1 复用 dev 的实施逻辑 |
| `/verify` | 验证 + G3 门禁 | deliver 的阶段 2 等价于 verify |
| `/archive` | 兼容补归档 | deliver 标准流程不单独使用 |
| `/commit` | 提交入库 | deliver 的最后一步等价于 commit |

**/deliver** = Dev（验收驱动循环 + TDD + 自动归档）+ Commit（提交入库），一气呵成完成从「design 就绪」到「代码入库」的全流程。
