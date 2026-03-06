---
name: /dev
id: dev
category: Workflow
description: 实施特性（SDD 第三阶段：逐 task 执行 + 每 task 自动 G2 卡点）
---

> SDD 主流程：explore → prd → design → **dev** → archive → commit → deploy

## 阶段准入自检（Dev Gate）

进入本阶段前，AI Agent **必须自检**以下问题。任何未通过 → 输出 `GATE_BLOCK`，暂停执行。

| # | 自检问题 | 通过条件 |
|---|---------|---------|
| V1 | design.md 是否存在且关键设计决策已冻结？ | 目标节点 design.md 已写入，无重大未决设计问题 |
| V2 | codegen 是否已通过？ | make verify-metadata + make codegen + make codegen-app 均已通过 |
| V3 | tasks.md 中是否有可执行的任务列表？ | 任务按 metadata→codegen→业务逻辑→测试 顺序排列，至少有一条待完成任务 |
| V4 | acceptance.yaml A1~An 是否已定义且有明确判定方式？ | 每条验收标准可测量，有明确通过/失败条件 |
| V5 | 节点层级是否符合规范？ | L4 默认叶子（见 `01_FEATURE_TREE_LEVEL_DEFINITIONS.md`） |

**任一未通过 → 输出 GATE_BLOCK：**

```
GATE_BLOCK（Dev 准入未满足）：
□ V1: design.md 不存在 → 先执行 /design 完成设计基线
□ V2: codegen 未通过 → 执行 make verify-metadata && make codegen && make codegen-app
（列出所有未通过项）
```

---

## 前置条件（GATE_BLOCK 触发时的补全列表）

```
前置条件不满足，请先完成以下项后再执行 /dev：

□ [ ] 目标节点目录存在，且具备 spec.md、design.md、tasks.md、acceptance.yaml（若未创建，先执行 /prd + /design）
□ [ ] G1 已通过：make verify-metadata、make codegen、make codegen-app 均已通过
□ [ ] tasks 已就绪：tasks.md 中有明确的当前交付任务，顺序为 metadata → codegen → 业务逻辑 → 测试
□ [ ] 需求已澄清：若需求仍不清晰，先执行 /explore 或 /prd 澄清后再实施

补全后重新执行：/dev
```

---

## 步骤

### 1. 加载 tasks

读取目标特性的 `tasks.md`，按顺序逐项执行。实现须符合 `spec.md` 与 `design.md`。

**强制开发顺序**：

```
contracts/metadata → make verify → make codegen → 业务逻辑 → 测试
```

如某个 task 涉及扩展操作（新实体/字段/事件等），先执行 `/extend`。

### 2. 逐 task 执行 + 自动 G2 卡点

每完成一个 task，AI Agent **必须立即自动执行**：

```bash
make build                     # 编译通过（云侧）
make test-contract             # 契约测试通过（云侧）
# 若变更含 quwoquan_app/lib/**/*.dart，追加：
flutter test test/cloud/ test/components/ test/ui/
```

**失败 → 停止当前 task → 输出错误 + 修复建议 → 修复后重跑 → 通过后继续下一个 task。**

### 3. 约束（实时强制）

| 端 | 约束 | 规则来源 |
|----|------|---------|
| Go | domain 禁止 import application/adapters/infrastructure | `01-arch-constraints` |
| Go | 仅 infrastructure + tests 可 import 数据库驱动 | `01-arch-constraints` |
| Go | 必须使用 runtime/errors、runtime/config、runtime/messaging | `01-arch-constraints` |
| Go | codegen 文件（DO NOT EDIT）禁止手改 | `01-arch-constraints` |
| Dart | 禁止硬编码视觉字面量（fontSize/EdgeInsets/Color/BorderRadius） | `02-dart-coding` |
| Dart | 禁止相对路径 import（必须 package:） | `02-dart-coding` |
| Dart | Feature 禁止直接 import 其他 Feature 内部 | `02-dart-coding` |
| 错误码 | 云侧用 generated.AppErrorFrom*；端侧用 *ErrorCode.fromCode().toDisplayMessage(l10n)；测试用枚举.code | `01-arch-constraints §3.3` |
| 端云 | Go struct / Dart DTO / OpenAPI / Migration 必须与 metadata 一致 | `01-arch-constraints` |
| **PA 契约** | 引擎逻辑禁止字段名字符串字面量；活跃 contractVersion ≤2 个；修改契约字段必须同步更新 `AssistantTurnOutput` 并使用 `/extend pa-contract` | `02-dart-coding §5` |

### 4. 全部 task 完成后

```bash
make gate                      # 本地门禁（verify + build + test-contract）
```

**通过 → 输出实施摘要 → 下一步：`/archive`（归档）或 `/commit`（归档+提交）。**

---

## 实施摘要格式

```
实施完成：<feature-path>

任务完成：N/N [x]
G2 卡点：全部通过

变更摘要：
  - <文件/模块>：<变更描述>
  ...

make gate：PASS

下一步：/commit（归档 + 提交入库）
      或 /archive（仅归档）
```

---

## 与其他命令的关系

| 命令 | 职责 | 与 /dev 关系 |
|------|------|------------|
| `/design` | 设计基线 + codegen | dev 的前置 |
| `/dev` | **逐 task 实施** | 消费 tasks.md，每 task 后 G2 |
| `/extend` | 增量扩展（新增字段/事件/端点） | dev 过程中发现需要扩展时调用 |
| `/archive` | 归档特性 | dev 完成后 |
| `/commit` | 归档 + 提交入库 | dev 完成后（推荐） |
| `/deliver` | dev + archive + commit 一气呵成 | deliver 的阶段 1 复用 dev 的实施逻辑 |
