---
name: sync-lane-from-dev
description: Bring the local dev integration branch (branch_policy integration_branch, currently dev1.0) into the current lane worktree by fast-forward or one merge, resolving conflicts only inside this lane. Use when the user says 同步 dev1.0, 拉齐开发分支, 合入最新代码到本地, 更新到最新, 从 dev 同步, or 解决与 dev 的冲突.
metadata:
  kind: workflow
  command: /sync-lane-from-dev
---

# sync-lane-from-dev

## 触发与输入

把本地开发集成分支同步进**当前 lane 工作树**，方向固定 dev → lane；不推送 lane、不移动开发分支、不进入 integration 工作区。开发分支默认取 `quwoquan_ops/policies/branch_policy.yaml#integration_branch`（当前 `dev1.0`，下文以此指代），用户显式指定时以用户为准，Skill 名不绑定版本。输入：当前工作区路径与分支、本地/远端 `dev1.0` 头、脏树与 untracked、进行中 merge/rebase 状态、用户明确目标。通道语义只读 `branch_policy.yaml#persistent_lane_admission`，落后阈值只读 `worktree_policy.yaml#resync_reminder_behind_commits`。

## 执行

1. PRE 校验 HEAD 是六条 `lane/*` 之一且工作区路径符合 `worktree_policy.yaml` 布局；在 `integration/`（`dev1.0`）上触发时停止并指向 `integrate-lane-to-dev`。`git fetch origin` 后记录相对本地/远端 `dev1.0` 的 ahead/behind、merge-base，以及是否存在 `MERGE_HEAD`/`rebase-merge`/`rebase-apply`。
2. 取本次同步会改动的路径（`git diff --name-only HEAD dev1.0`）与 `git status --porcelain` 的脏文件/untracked 求交；有重叠即 `GATE_BLOCK` 并列出文件，不 stash、不 reset、不 checkout 覆盖。
3. lane 是 `dev1.0` 祖先时 `git merge --ff-only dev1.0`；否则 `git merge dev1.0`（普通 merge，不 rebase/squash），只在本 lane 解决冲突：逐文件保留双方语义，contracts/metadata 冲突先改 authoring source 再 verify/codegen，生成物冲突以重新生成为准，冲突文件之外的字节不动。
4. 对冲突路径与被同步的 `contracts/**`、generated、gate/policy 路径运行影响面最小且足够的 focused local_contract/verify；merge commit 消息写明来源 `dev1.0` 头、冲突文件数与解决方式。
5. 完成后重新读取 ahead/behind 与 status，确认 lane 已包含 `dev1.0` 头且脏树只剩同步前已有字节；不自动 push，push/合入回 dev 均需用户另行授权。

## 完成证据

同步前后 HEAD、`dev1.0` 头、ahead/behind、采用的路径（`ff-only` 或 `merge`）、merge commit SHA（若有）、冲突文件清单与逐文件解决方式、focused 验证命令与退出码、同步后 status 摘要。本地 PASS 不代表 dev 合入、Alpha 或准出。

## 失败与停止

不在 lane 分支、工作区与布局不匹配、进行中 merge/rebase、脏文件或 untracked 与同步路径重叠、冲突无法在本 lane 内保留双方语义、focused 验证失败时 `GATE_BLOCK`：保留首个 typed blocker 与当前 Git 状态，不 reset/stash/clean/`--abort` 他人字节，不用 `-X ours/theirs` 整体覆盖，不把未验证 merge 冒充完成。

## 条件性交接

用户在同一请求中明确要求提交时交 `commit`；要求合入 dev 时以指令交接 `integrate-lane-to-dev`（在 integration 工作区运行 `/integrate-lane-to-dev`），不在本 lane 工作区代跑、不 `cd` 到其他 worktree。持久交接语义见 continue Skill。
