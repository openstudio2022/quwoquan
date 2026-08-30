---
name: commit
description: Create a git commit for a reviewed increment - secret and ownership checks, staging only related files, L0 commit gate, repository-style message, post-commit status verification. Use only when the user explicitly asks to 提交, commit, or 创建提交.
metadata:
  kind: workflow
  command: /commit
---

# commit

## 触发与输入

只在用户明确要求创建 Git commit 时使用。输入是已评审的本次增量、当前 HEAD/status、本 scope 文件清单和最近有效 POST 证据。



自然语言触发与显式 Skill 调用同轨，字段、闭集与审计隔离只引用 `quwoquan_ops/policies/human_agent_delivery_contract.yaml#workflow_interaction_binding.commit`：

- PRE：`decision_request` / `integration_trusted_ci` / `engineering_delivery_owner`。

## 执行

1. 重新检查 branch、HEAD、脏树、untracked、可疑 secret/PII、所有权与并行 writer；不纳入任务外文件。
2. 仅用显式 pathspec 暂存当前 scope，检视 staged diff 与生成物身份。
3. 执行 L0 `quwoquan_ops/gate/commit_gate.sh`；不把 `--no-verify` 当常规通道。按仓库风格生成中文信息并提交。
4. 提交后核对新 SHA、提交文件与剩余工作树，不清理他人变更。

- 执行中：`exception_escalation` / `integration_trusted_ci` / `engineering_delivery_owner`。

`$route` 表示按当前决定责任动态路由；Skill 不复制 envelope schema，所有可见输出统一由 canonical projector 生成。

## 完成证据

交付 commit SHA、message、精确文件列表、L0 命令/退出码和提交后 status。本地 commit gate 不代表 CI、runtime、release 或 UAT 通过。

- POST：`completion_report` / `integration_trusted_ci` / `engineering_delivery_owner`。

## 失败与停止

无用户明确授权、POST 证据缺失/过期、secret/所有权风险、无法精确暂存或 L0 失败时 `GATE_BLOCK`，不创建提交。不 reset、clean 或覆盖来消红。

## 条件性交接

六类触发（跨会话未完成、多人并行、环境/发布、外部阻断、证据复用、用户显式要求）统一调用 canonical handoff producer；普通闭环不落持久交接。

仅当路由结果要求真实人类责任时，使用统一 `$route`、project/card 与 hosted authority readback；routine execution 不新造 checkpoint。Reviewer PASS 只是评审证据，不能签发或替代 authority receipt。
