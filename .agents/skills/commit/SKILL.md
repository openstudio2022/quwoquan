---
name: commit
description: Create a git commit for a reviewed increment - secret and ownership checks, staging only related files, L0 commit gate, repository-style message, post-commit status verification. Use only when the user explicitly asks to 提交, commit, or 创建提交.
metadata:
  kind: workflow
  command: /commit
---

# commit

提交已通过评审的增量并复核门禁与工作树状态。五段执行契约见根 `AGENTS.md`。

## 触发

- 显式命令 `/commit`，或用户明确要求提交。
- [MUST NOT] 未经用户要求主动提交。

## 输入

- 最近一次通过的 POST 评审 HANDOFF（无通过结论即停止，先回对应工作流补评审）。
- `git status` / `git diff` / `git log`（并行取得）与待提交文件范围。

## 角色

主会话扮演 **committer**，受 Git 安全协议约束：不改 git config，不做破坏性操作。

## 执行

自由度：低（固定序列）。

1. 并行读 `git status`、`git diff`、`git log`（对齐仓库提交信息风格）。
2. 检查待提交范围：不含秘密文件（`.env`、credentials 等）；不含未归属或与本任务无关的
   并行会话改动——**脏工作树是常态**，只暂存相关文件。
3. 暂存相关文件并提交；提交信息用中文、聚焦 why、遵循仓库风格。
   本地 pre-commit 走 L0 `quwoquan_ops/gate/commit_gate.sh`
   （目标 ≤10 分钟，硬顶 15 分钟）；全量 local_contract 由 CI Delivery Gate 分片承接。
4. 提交后复核 `git status` 确认成功与剩余工作树状态；
   本地失败摘要见 `.qwq_output/env/repo/runs/commit-gate/`。

## 交付件

**提交回执**：commit id、提交范围、门禁结果和剩余工作树状态。

送审前自检：提交内容与 HANDOFF 产出物清单一致；无秘密文件；无无关改动混入。

## 内置评审

- PRE：消费已有 POST 评审结论，无通过结论即 `GATE_BLOCK`。
- POST：L0 commit gate 即本工作流的 POST 证据，不再另派 reviewer。

## 失败与停止

- [MUST NOT] 自动 push；[MUST NOT] 把 `--no-verify` 当常规合入手段；
  [MUST NOT] 提交无关改动。
- 提交失败或被 hook 拒绝：修复后创建**新**提交，不得 amend。
- 提交无验收、无测试证据或未处置 `OPEN block` 的增量：`GATE_BLOCK`。

## HANDOFF

- **产出物**：提交回执。
- **未决项去向**：剩余工作树状态与未提交残量如实列出。
- **唯一合法下游**：报告给用户（用户要求 push / PR 时按其明确指令执行）。
- **证据链**：commit gate 输出、`git status` 复核结果。
