---
name: review
description: Build a bounded evidence-first Review plan from the shared owner manifest, dispatch one workflow primary and at most one profile specialist at POST, and consolidate typed GATE_BLOCK / PR_WARN / advisory results. Use whenever the user asks for 评审, 审核, 检视, plan review, code review, 验证, or 准出检查.
metadata:
  kind: workflow
  command: /review
---

# review

## 触发与输入

用户要求评审/验证/准出，或有自动 Review 的工作流进入 POST 时使用。PRE 只用主会话检查 owner、scope、验收和 evidence 可执行性，不派 Reviewer。

必要输入：

- `workflow`、`segment=PRE|POST`、`deliverable`、`scope`。
- `make feature-context TARGET=<path>` 生成的当前 context manifest。
- 排序去重的 `changed_paths`，包含 tracked、untracked 和已删除目标。
- re-review 时额外给 initial `plan.json` 和 1–2 个 `finding-owner`。

registry 唯一声明 workflow primary、profile specialist、预算和命名 evidence：
`.agents/skills/review/references/registry.yaml`。Reviewer 的中性执行语义来自
`references/reviewer-executor.md`。manifest、plan、terminal 和 tracked projection schema 来自
`quwoquan_ops/policies/agent_governance_contract.yaml`，Cursor/Codex adapter 仅是生成投影。

## 执行

1. **解析 owner**：Review POST 必须消费与开发 PRE 相同的 manifest；profile 只选 specialist/evidence，不重新定义 Feature owner。
2. **生成 plan**：

   ```bash
   python3 quwoquan_ops/cli/review_dispatch.py \
     --workflow <workflow> --segment <PRE|POST> \
     --deliverable <deliverable> --scope <scope> \
     --context-manifest <manifest.json> \
     --changed-paths <path...> --out <run-dir>
   ```

   PRE 的 `reviewers`/`evidence` 必须为空。POST 只选 workflow primary 和数值 priority 最高的一名 specialist，同优先级按 registry 顺序裁决；`explore/plan-next/continue/review/commit` 作为控制型 workflow 默认为零。
3. **先取证**：主会话按 `plan.evidence` 的 ID 去重执行每条命令一次，记录退出码与当前指纹。required evidence 失败时立即停止，不启动 Reviewer。
4. **派审**：并行与调用预算只读取 registry 的 `limits`。每个 Reviewer 只获得 plan 列出的 contexts、角色视角、当前 workflow checklist、grading 和已有 evidence；不加载未选 profile/功能规则。Reviewer 不修复、不发布、不自行补跑 gate；证据缺失时返回 incomplete。
5. **汇总**：按 `grading.md` 合并重复 finding，保留最高等级、精确 path/anchor、finding owner 和恢复动作。不自动进行第二轮复审或超时重试。
6. **定向复审**：修复后只能直接引用 initial plan，为首次 Reviewer 中的 finding owner 生成 `--round rereview --finding-owner <role>`。initial、复审与累计调用上限均读取 registry `limits`；不允许 rereview chain。

## 完成证据

完整 `plan.json` 必须符合 canonical agent governance contract。交付每条 evidence 的实际结果、每个已启动角色的完成/不完整状态、去重 finding 与最终 typed 等级。

只有 required evidence 全部通过、required Reviewer 完成、指纹仍匹配且无 `GATE_BLOCK` finding 时才可准出。optional specialist incomplete 可产生 `PR_WARN`，但不得记为它已通过。

## 失败与停止

- evidence、Reviewer、取消、指纹与 scope 失败只按 canonical contract 的 `terminal_codes` 返回等级、自动重试许可与唯一恢复动作；未知 terminal fail-closed。
- 不自动重试 incomplete Reviewer，不复用 stale evidence，不把 optional incomplete 或 cancelled 包装为完整通过。
- 无效 finding owner、复审链或角色调用超出 registry limits 时 typed 拒绝，不扩大 reviewer 集合。

## 条件性交接

普通闭环 Review 只交付 plan 身份、证据、finding 和未决项。只有跨会话未完成、环境/发布、多人并行、外部阻断或证据需复用时，才持久化 `plan.json`、evidence 回执、finding-owner、指纹、incomplete 终态和唯一恢复动作。
