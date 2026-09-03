---
name: commit
description: Create a git commit for the current increment - secret and ownership checks, staging only related files, L0 commit gate, repository-style message, post-commit status verification. Use only when the user explicitly asks to 提交, commit, or 创建提交.
metadata:
  kind: workflow
  command: /commit
---

# commit

## 触发与输入

只在用户明确要求创建 Git commit 时使用。输入是用户明确要求、当前 HEAD/status 与精确 scope；lane 提交不要求 Review evidence，评审在 lane→`dev1.0` PR 准出时进行。角色交互只引用 `quwoquan_ops/policies/human_agent_delivery_contract.yaml#workflow_interaction_binding.bindings.commit`，可见输出由 canonical projector 生成。

## 执行

1. PRE 确认用户明确要求提交与精确 scope；若存在本轮 owner manifest / Review evidence 则一并引用，缺失不阻断，不在 commit 生成替代证据。
2. 重新检查 branch、HEAD、脏树、untracked、secret/PII、所有权与活跃 writer，只用显式 pathspec 暂存当前 scope。
3. 检视 staged diff 与生成物身份，执行 L0 `quwoquan_ops/gate/commit_gate.sh`；pre-commit 的 staged boundary 与 L0 都不用 `--no-verify` 绕过。
4. 按仓库风格提交，随后核对 SHA、提交文件与剩余工作树，不清理他人变更。

## 完成证据

交付 commit SHA、message、精确文件列表、L0 命令/退出码和提交后 status，并如实标注是否已评审；本地 PASS 不代表 CI/runtime/release/UAT。

## 失败与停止

无明确授权、secret/所有权风险、无法精确暂存、staged boundary 或 L0 失败时 `GATE_BLOCK`，不创建提交。

## 条件性交接

提交后仅按用户授权进入 push/PR/发布；只有 canonical 六类 handoff 触发成立时持久交接。
