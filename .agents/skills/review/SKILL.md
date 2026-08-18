---
name: review
description: Dispatch role-based parallel review for a given workflow, deliverable, and derived profiles, run the deduplicated test/gate evidence plan, then consolidate findings into GATE_BLOCK / PR_WARN / advisory. Called automatically at each workflow's PRE and POST, and whenever the user asks for 评审, 审核, 检视, plan review, code review, 验证, or 准出检查 in this repository.
metadata:
  kind: workflow
  command: /review
---

# review

按 `(workflow, deliverable, profiles)` 装配角色 checklist bundle，执行去重后的证据计划，
并行派发只读 reviewer，汇总后交回调用方。**board 自己不做技术判断**，
只负责装配、取证、派发、汇总。五段执行契约见根 `AGENTS.md`。

## 触发

- 每个工作流的 PRE 与 POST 自动调用（参数由该工作流 SKILL.md 的「内置评审」段固定给出）。
- 显式命令 `/review`，或用户说评审、审核、检视、验证、准出检查——按其描述推断
  workflow 与 deliverable，推断不出就问，不要默认全角色。

## 输入

缺 `workflow` 或 `segment` 不开工，先补齐：

```yaml
workflow: dev                 # explore|prd|design|dev|plan-next|commit|environment-ops|content-production|incident-inspection
segment: POST                 # PRE|POST
deliverable: implementation   # 见 registry.yaml 的 deliverables
scope:
  in: 内容详情页新增收藏按钮
  out: 收藏列表页、收藏推送
changed_paths:                # POST 必填，PRE 可为计划中的路径
  - quwoquan_app/lib/service/content_service/.../content_detail_page.dart
```

## 角色

- **board**（本文件）：解析请求 → 派生 profile → 查 `references/registry.yaml` 装配 bundle →
  执行证据计划 → 并行派发 → 汇总。
- **reviewer**：通用只读执行体（`.claude/agents/reviewer.md`），同一定义启动多个实例，
  人设与 checklist 由派发 prompt 注入。只评价交付件，不执行生产、修复、发布或环境操作。
- 角色库：`references/roles/<role>/`，`ROLE.md` 定职责与盲区，
  `checklists/<workflow>/{base,<profile>}.md` 放带分级的可执行判定，
  `references/` 放该角色拥有的未分级知识。

## 执行

自由度：低（装配与派发是固定序列）。

1. 由 `changed_paths` 与 `deliverable` 按 registry 的 `profiles` 规则派生 profile 集合。
2. 按 registry 中该 workflow 的 binding 逐条求值 `when`，装配每个命中角色的
   base + profile checklist；未匹配 profile 的角色不派发。
3. `changed_paths` 命中 `triggers` 时追加对应领域角色。
4. **POST 先取证再评审**：从选中 bundle 收集全部 `gate:` 命令，去重后执行一次，
   形成 evidence map；测试结果是证据，文档状态不是。任何失败先归因四选一：
   `本计划引入 / 并行会话中间态 / 存量债 / 环境 flaky`，归因需基线对照证据
   （HEAD 重跑、`git log --follow`、复跑）。并行中间态如实交接，**不修不掩盖**。
   环境阻塞（URL、token、容器、凭证缺失）如实报告并说明影响的证据层，
   [MUST NOT] 静默跳过或用静态声明代替执行。
5. 按「先规格符合性、再质量」两阶段并行派发只读 reviewer（`concurrency.max_parallel` 分批）。
   **派发 prompt 必须自包含**：子代理不继承主会话技能与推理历史，只拿交付件、
   显式文件路径与共享 evidence。模板：

   ```text
   你是 quwoquan 仓库的评审角色 <role>。只读评审，不要修改任何文件。

   依据文件（请先全部读完，这是你本次评审的全部依据）：
   - .agents/skills/review/references/roles/<role>/ROLE.md
   - .agents/skills/review/references/roles/<role>/checklists/<workflow>/<checklist>.md
   - .agents/skills/review/references/grading.md

   评审请求：
   - workflow: <workflow> / segment: <segment> / deliverable: <deliverable>
   - scope in: <...> / scope out: <...>
   - 变更范围：<changed_paths 逐行>
   - 共享 gate 证据：<evidence id 与结果摘要；证据已由 board 执行，不要重复跑>

   要求：
   1. 只评审 checklist 里 <segment> 段的条目，逐条给结论。
   2. 每条 finding 必须带证据（文件:行，或引用共享 evidence id）。拿不出证据的不要提交。
   3. 条目带 gate: 且共享证据未覆盖的，实际把该命令跑一遍再下结论。
   4. 不要评审 ROLE.md「已知盲区」里的内容。
   5. 按 grading.md 的格式输出，最后给一行汇总计数。
   ```

## 交付件

**评审报告**：evidence map（含失败归因）、逐条带证据 finding、冲突与未完成角色、
整体准入/准出结论。汇总格式：

```text
review | workflow=dev segment=POST | profiles=dart-app,flutter-page | 角色 4 个
GATE_BLOCK 2 条 | PR_WARN 3 条 | 提示 1 条

[GATE_BLOCK] architect dev#3 — ...
[PR_WARN]   ux dev#2 — ...
```

送审前自检：evidence map 覆盖 bundle 内全部 gate；无证据 finding 已剔除；
未完成角色已如实列出。

## 内置评审

本工作流即评审本体，不嵌套评审自身；`grading.md` 与 registry 的结构正确性由
`make verify-agent-context-budget` 门禁守护。

## 失败与停止

- 有 `GATE_BLOCK` → 整体 `GATE_BLOCK`，调用方必须先修复再继续。
- 只有 `PR_WARN` → 调用方逐条显式裁决「修复 / 转 `OPEN-###` / 判 Out of Scope」，不允许静默略过。
- 角色结论冲突 → board 不自行裁决，原样并列呈报并标注冲突点。
- 角色执行失败或超时 → 如实报告未完成，不得用其他角色结论替代，也不得因此判整体通过。
- evidence 缺失或失败 → [MUST NOT] 包装为通过；board 不吞 finding。

## HANDOFF

- **产出物**：评审报告，回填调用方工作流的 HANDOFF。
- **未决项去向**：PR_WARN 裁决结果与未完成角色由调用方承接。
- **唯一合法下游**：调用方工作流（`GATE_BLOCK` 时调用方停在 DURING）。
- **证据链**：evidence map、各 reviewer 原始输出。

## 扩展

- 加角色：建 `references/roles/<role>/ROLE.md` 与所需 `checklists/<workflow>/<profile>.md`，
  在 `registry.yaml` 注册 binding。
- 加 profile：在 registry 的 `profiles` 声明路径规则，为相关角色补 checklist。
- 改完跑 `make verify-agent-context-budget` 校验分级、gate 存在性、映射与可达性。
