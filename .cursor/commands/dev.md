---
name: /dev
id: dev
category: Workflow
description: 实施特性（SDD 第三阶段：逐 task 执行，完成四层自验证并自动归档，等待提交）
---

> SDD 主流程：explore → prd → design → **dev** → commit → deploy

## 阶段准入自检（Dev Gate）

进入本阶段前，AI Agent **必须自检**以下问题。任何未通过 → 输出 `GATE_BLOCK`，暂停执行。

| # | 自检问题 | 通过条件 |
|---|---------|---------|
| V1 | design.md 是否存在且关键设计决策已冻结？ | 目标节点 design.md 已写入，无重大未决设计问题 |
| V2 | codegen 是否已通过？ | make verify-metadata + make codegen + make codegen-app 均已通过 |
| V3 | 当前 Story 是否有可执行的 tasks 清单？ | tasks 按 metadata→codegen→业务逻辑→测试 顺序排列，至少有一条待完成任务 |
| V4 | acceptance.yaml A1~An 是否已定义且有明确判定方式？ | 每条验收标准可测量，并映射到 `T1~T4` |
| V5 | 节点层级是否符合规范？ | L4 默认叶子（见 `01_FEATURE_TREE_LEVEL_DEFINITIONS.md`） |
| V6 | 当前待实现 task 是否已绑定“先失败后转绿”的测试？ | 至少存在一个 Red 阶段测试入口 |
| V7 | 若为实时性/高风险交互，是否已绑定弱网/并发/恢复类用例？ | 关键 NFR 不会被实现阶段遗漏 |
| V8 | 若涉及 operation / surface / route，是否已完成 metadata 与 codegen 基线，且 consumer 不再依赖代码 override 表？ | 实施阶段只消费生成常量 |

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
□ [ ] tasks 已就绪：tasks.md 中有明确的当前交付任务，顺序为 metadata → codegen → 测试先行 → 业务逻辑 → 重构
□ [ ] 需求已澄清：若需求仍不清晰，先执行 /explore 或 /prd 澄清后再实施

补全后重新执行：/dev
```

---

## 步骤

### 1. 加载 tasks

读取目标特性的 `tasks.md`，按顺序逐项执行。实现须符合 `spec.md` 与 `design.md`。

**实施单位**：L4 Story。`tasks.md` 是 Story 的工程执行清单，不是新的树层级。

**强制开发顺序**：

```
contracts/metadata → make verify → make codegen → 先写测试(Red) → 最小实现(Green) → 重构(Refactor)
```

如某个 task 涉及扩展操作（新实体/字段/事件等），先执行 `/extend`。

### 2. 逐 task 执行 + 自动 G2 卡点

每个 task 必须按下列循环执行：

```text
1) 读取该 task 对应的 A1~An 与 T1~T4
2) 先补最小失败测试（Red）
3) 运行测试，确认失败原因与目标一致
4) 编写最小实现（Green）
5) 重跑测试，确认转绿
6) 进行必要重构（Refactor）
7) 记录测试证据、弱网/并发/灰度补充项
```

每完成一个 task，AI Agent **必须立即自动执行**：

```bash
make build                     # 编译通过（云侧）
make test-contract             # 契约测试通过（云侧）
# 若变更含 quwoquan_app/lib/**/*.dart，追加：
flutter test test/cloud/ test/components/ test/ui/
```

**失败 → 停止当前 task → 输出错误 + 修复建议 → 修复后重跑 → 通过后继续下一个 task。**

**补充要求**：
- 不允许“先写完整功能，再一次性补测试”
- 若 Red 阶段无法稳定失败，说明测试不可用，必须先修正测试设计
- 若需求含实时性或弱网诉求，必须在 task 内同步落地相关 T2/T3/T4 证据，不得留到归档前补救
- 若需求含 API/Router/Telemetry 标识迁移，必须先迁 metadata/codegen，再迁 consumer；禁止在业务代码里额外维护 route/page/surface/operation 常量表

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
| Dart | Repository / Router / decoder context 禁止硬编码业务 path、pageId、surfaceId、operationId、route path | `01-arch-constraints` |
| 错误码 | 云侧用 generated.AppErrorFrom*；端侧用 *ErrorCode.fromCode().toDisplayMessage(l10n)；测试用枚举.code | `01-arch-constraints §3.3` |
| 端云 | Go struct / Dart DTO / OpenAPI / Migration 必须与 metadata 一致 | `01-arch-constraints` |
| **PA 契约** | 引擎逻辑禁止字段名字符串字面量；活跃 contractVersion ≤2 个；修改契约字段必须同步更新 `AssistantTurnOutput` 并使用 `/extend pa-contract` | `02-dart-coding §5` |
| 实时性 | 必须验证时延目标、顺序一致性、幂等、重试、断线恢复 | `03-testing` |
| 弱网/弹性 | 必须验证高延迟、抖动、短断网、降级、回退、限流与恢复 | `03-testing` |
| 对标体验 | 关键交互不得低于 design/spec 中定义的一流体验基线 | `spec.md` / `design.md` |

### 4. 全部 task 完成后：四层自验证 + deploy-ready + 自动归档

```bash
make gate-full                 # 四层自验证 + 非功能验收 + 发布前证据
```

开发完成后，AI Agent **必须自动完成**：
- `T1~T4` 四层自验证证据收口
- 非功能验收（实时性 / 弱网 / 并发 / 弹性 / 体验）收口
- gray-release ready 检查：灰度步进、SLO、观测、回滚条件齐全
- 自动回写归档状态：`acceptance.yaml.archived=true`、`acceptance.yaml.archived_at=<ISO8601>`、`tree_index.status=completed`

**通过 → 自动归档完成 → 等待 `/commit` 提交。**

---

## 实施摘要格式

```
实施完成：<feature-path>

任务完成：N/N [x]
TDD 循环：全部完成（Red → Green → Refactor）
G2 卡点：全部通过
G3 收口：make gate-full PASS
归档状态：已自动完成

变更摘要：
  - <文件/模块>：<变更描述>
  ...

非功能证据：
  - 实时性/弱网/并发/灰度：<已补齐的证据>

发布就绪：
  - gray-release ready：PASS

make gate-full：PASS

下一步：/commit（提交入库）
```

---

## 与其他命令的关系

| 命令 | 职责 | 与 /dev 关系 |
|------|------|------------|
| `/design` | 设计基线 + codegen | dev 的前置 |
| `/dev` | **逐 task 实施 + 自验证 + 自动归档** | 消费 tasks.md，每 task 后 G2，收口时完成 G3 |
| `/extend` | 增量扩展（新增字段/事件/端点） | dev 过程中发现需要扩展时调用 |
| `/archive` | 兼容补归档 | 标准流通常不需要；仅手动修复时使用 |
| `/commit` | 提交入库 | dev 完成后直接执行 |
| `/deliver` | dev + commit 一气呵成 | deliver 复用 dev 的自动归档能力 |
