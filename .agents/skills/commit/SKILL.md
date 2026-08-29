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

## 执行

1. 重新检查 branch、HEAD、脏树、untracked、可疑 secret/PII、所有权与并行 writer；不纳入任务外文件。
2. 仅用显式 pathspec 暂存当前 scope，检视 staged diff 与生成物身份。
3. 执行 L0 `quwoquan_ops/gate/commit_gate.sh`；不把 `--no-verify` 当常规通道。按仓库风格生成中文信息并提交。
4. 提交后核对新 SHA、提交文件与剩余工作树，不清理他人变更。

## 完成证据

交付 commit SHA、message、精确文件列表、L0 命令/退出码和提交后 status。本地 commit gate 不代表 CI、runtime、release 或 UAT 通过。

## 失败与停止

无用户明确授权、POST 证据缺失/过期、secret/所有权风险、无法精确暂存或 L0 失败时 `GATE_BLOCK`，不创建提交。不 reset、clean 或覆盖来消红。

## 条件性交接

提交本身用简短交付。只有提交后仍有跨会话、发布/环境或外部阻断时，才持久化 SHA、剩余 scope、证据指纹和唯一后续动作。
