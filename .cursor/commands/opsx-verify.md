---
name: /opsx-verify
id: opsx-verify
category: Workflow
description: 验证实现匹配基线制品 + 基线漂移检测 + 自动 G3 门禁
---

> 主线：`specs/00_MASTER_DEVELOPMENT_FLOW.md` — 阶段 4
>
> **核心职责**：deliver/apply 完成后，检测实现与基线（spec/design/tasks/acceptance）之间的漂移，
> 并强制要求所有 A1~An status 在归档前达到 `implemented`/`waived`/`deferred`。

---

## 步骤

### 步骤 1：完成度检查

1. 确认目标节点具备四类文档：`spec.md`、`design.md`、`tasks.md`、`acceptance.yaml`
2. 读取 `tasks.md`，统计完成状态：
   - `[x]`（已完成）/ `[ ]`（未完成）按三个区块分别统计：当前交付任务、搁置任务、未来演进任务
   - **阻塞条件**：当前交付任务中存在未完成 `[ ]` → 输出 BLOCKING，列出所有未完成条目
3. 读取 `acceptance.yaml`，统计 A1~An status 分布：
   - `pending` 数量、`implemented` 数量、`waived` 数量、`deferred` 数量
   - **阻塞条件**：存在 status=`pending` → 输出 BLOCKING，列出所有 pending 项
4. 生成完成度报告

---

### 步骤 2：基线漂移检测（Baseline Drift Detection）

> 这是 deliver/apply 后的关键步骤。检测实现与基线之间的四类漂移。

#### 漂移类型 D1：SPEC 漂移（实现少于 spec）

逐条读取 `spec.md` 的功能说明与约束，与 `acceptance.yaml` A1~An 对比：
- 检查 spec 中描述的每个功能点是否有对应的验收项（A_）覆盖
- 若 spec 功能点无对应验收项 → 输出 `SPEC_DRIFT`：spec 描述了但验收未覆盖

#### 漂移类型 D2：IMPL 漂移（实现多于 spec）

读取本次变更的文件列表（`git diff --name-only HEAD`），识别新增功能路径：
- 比对 spec.md 的范围声明：新增文件/功能是否在 spec 范围内
- 若实现了 spec 未提及的功能 → 输出 `IMPL_DRIFT`：建议补充到 spec 或明确为 out-of-scope

#### 漂移类型 D3：DESIGN 漂移（实现决策偏离 design）

读取 `design.md` 的关键设计决策，与当前实现对比：
- 检查 design 中确定的方案（如存储选型、分层结构、协议格式）是否与代码一致
- 若实施中改变了 design 决策但未回写 → 输出 `DESIGN_DRIFT`：提示更新 design.md

#### 漂移类型 D4：TASK 漂移（实施中产生的未跟踪任务）

比对 `tasks.md` 的原始任务列表与 `git diff` 中的变更：
- 若变更中的关键文件在 tasks.md 中无对应任务条目 → 输出 `TASK_DRIFT`
- 常见情形：实施中临时添加的修复或调整未记入 tasks，导致任务清单与实际工作量不符

**漂移处理原则**：
- D1/D2/D3 必须在归档前解决（更新制品或确认超出范围）
- D4 建议修复（补充 tasks.md），不阻塞归档，但输出 WARNING

---

### 步骤 3：验收项测试链接验证

逐条检查 `acceptance.yaml` 中每个 `status=implemented` 的验收项：
1. `tests[].file` 所列文件在仓库中存在
2. `tests[].functions` 所列函数名在对应文件中存在（通过文本检索）
3. 若文件或函数不存在 → 输出 `TEST_LINK_BROKEN`，视为 BLOCKING

对 `tests[]` 为空的 `implemented` 项 → 输出 WARNING：`A_N 声明为 implemented 但 tests[] 为空，建议补充测试链接`

---

### 步骤 4：正确性检查（AI 辅助）

1. 确认实现符合 `spec.md` 的需求描述
2. 确认实现符合 `design.md` 的设计决策
3. 确认代码遵循 DDD 分层 + metadata-first + runtime 统一
4. 确认 `tasks.md` 的「搁置任务」每项有明确的重启条件（非「待定」）
5. 确认 `tasks.md` 的「未来演进任务」与 `design.md` 的「未来演进」章节对应

---

### 步骤 5：自动 G3 卡点：全量门禁

AI Agent **必须自动执行**：

```bash
make gate-full
```

包含（现有）：
- `make verify-metadata` — metadata 一致性
- `make build` — 全量编译
- `make test-contract` — 契约测试
- DDD 结构约束、codegen hash、端侧语义

包含（新增，由 `gate.sh check-feature-tree-consistency` 提供）：
- 特性树结构一致性：`tree_index.yaml` ↔ 目录存在性
- 四类文档完整性：每个节点具备 spec/design/tasks/acceptance
- acceptance.yaml 归档前状态检查：无 `pending` 项
- acceptance.yaml tests 链接验证：`implemented` 项的 tests[] 文件/函数存在

**任一失败 → 输出错误 + 修复建议 → 修复后重跑。**

---

### 步骤 6：输出漂移报告与验证报告

```
验证报告：<feature-path>

━━━ 完成度 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
任务完成：当前交付 N/N [x]，搁置 N 项，演进 N 项
验收状态：implemented N，waived N，deferred N，pending N

━━━ 漂移检测 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SPEC_DRIFT:    [无 | N 项需处理]
  ↳ spec.md §3 提及「XXX」，但无对应验收项覆盖
IMPL_DRIFT:    [无 | N 项需确认]
  ↳ lib/ui/discovery/widgets/new_widget.dart 未在 spec 范围内，建议补充或标注 out-of-scope
DESIGN_DRIFT:  [无 | N 项需回写]
  ↳ design.md §2 决策「使用 PhotoPostDto.aspectRatio」已实现，但 design 中未更新演进状态
TASK_DRIFT:    [无 | N 项 WARNING]
  ↳ lib/cloud/content/generated/content_errors.g.dart 无对应 tasks 条目

━━━ 测试链接 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
A1: implemented ✓ → test/cloud/content/feed_item_dto_contract_test.dart::generates_from_metadata ✓
A3: implemented ✓ → tests[] 为空 ⚠ 建议补充测试链接
A5: implemented ✓ → test/features/content/post_view_projection_contract_test.dart::discovery_state_is_list_of_post_base_dto ✓

━━━ 门禁 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
make gate-full: PASS / FAIL

━━━ 结论 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BLOCKING: N 项（必须修复后才能归档）
WARNING:  N 项（建议修复，不阻塞归档）

→ Ready for /opsx-archive
→ 或：修复以下 BLOCKING 项后重跑 /opsx-verify：
  1. acceptance.yaml A2 status=pending → 完成实现后改为 implemented
  2. A4 tests[] 文件不存在：test/cloud/content/xxx_test.dart
```

---

## 附：基线同步操作（漂移修复指引）

| 漂移类型 | 修复操作 |
|----------|----------|
| SPEC_DRIFT（spec 有但验收未覆盖） | 补充 acceptance.yaml 对应 An 项，或在 spec.md 标注「超出当前范围」 |
| IMPL_DRIFT（实现超出 spec） | 补充 spec.md 范围描述，或将该实现标注为 out-of-scope 并计划回滚/迁移 |
| DESIGN_DRIFT（设计决策变更未回写） | 更新 design.md 对应决策，标注「实施阶段调整」及原因 |
| TASK_DRIFT（新增工作未跟踪） | 在 tasks.md 补充对应任务（已完成则直接标 `[x]`） |
| TEST_LINK_BROKEN | 修复 acceptance.yaml tests[] 路径，或补写测试后填入 |
| pending 项未解决 | 实现后改 status=implemented（填 tests[]），或改为 deferred（补 tasks.md 搁置条目） |
