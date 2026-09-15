---
name: sync-lane-from-dev
description: Sync only the current local lane identity from the exact origin/dev1.0 SHA frozen after fetch, normally by fast-forward; a diverged lane needs explicit merge authorization. Never consume unpublished local dev or push lane refs. Use when the user says 同步 dev1.0, 拉齐开发分支, 合入最新代码到本地, 更新到最新, 从 dev 同步, or 解决与 dev 的冲突.
metadata:
  published_baseline: origin/dev1.0 frozen after fetch
  kind: workflow
  command: /sync-lane-from-dev
---

# sync-lane-from-dev

## 触发与输入

把已发布的 `origin/dev1.0` 同步进**当前 lane 工作树**，方向固定远端 dev → 本地 lane。六条本地 `lane/*` 只作检出/验收身份；不推 lane、不移动本地 dev、不进入 integration 工作区。开发分支只读 `branch_policy.yaml#integration_branch`（当前 `dev1.0`）；不接受用本地未发布 dev 替代远端基线。输入：当前工作区路径与分支、fetch 后冻结的 published SHA、脏树/untracked、进行中 Git 操作及用户授权。布局与落后阈值只读 `worktree_policy.yaml`。

## 执行

1. PRE 校验 HEAD 是六条 `lane/*` 之一且工作区路径符合策略；在 `integration/` 触发时停止并交 `integrate-lane-to-dev`。确定 exact target，运行 `make feature-context TARGET=<exact-path>` 并取得唯一 current owner identity ref；写入前声明 exact path scope 并核对活跃 claim。`git fetch origin` 成功后仅一次用 `git rev-parse --verify refs/remotes/origin/dev1.0^{commit}` 冻结 `published_sha`；记录 HEAD、该 SHA、ahead/behind、merge-base、status 与进行中 merge/rebase/cherry-pick/revert。fetch 或远端 ref 解析失败立即阻断，绝不 fallback 本地 `dev1.0`。
2. 只以 `git diff --name-only HEAD <published_sha>` 计算本轮同步路径，与脏文件/untracked（含 rename 两端及目录父子路径）检查重叠。进行中操作、claim 冲突或脏重叠均 `GATE_BLOCK`，保持 HEAD/index/WIP 原字节，不默认清理。
3. 以 `git merge-base --is-ancestor HEAD <published_sha>` 判定：祖先仅执行 `git merge --ff-only <published_sha>`。分叉默认停止；只有用户明确授权**当前 lane 合并该 published SHA**时才可 `git merge --no-commit --no-ff <published_sha>`，不 rebase/squash，不代其他 lane 解冲突。保留双方语义，contracts/metadata 冲突先改 authoring source 再 verify/codegen；生成物只重新生成。需要 merge commit 时仍须明确提交授权并交 `commit`；未提交、未重新验收不得称完成。
4. 对同步影响与冲突路径运行最小充分 focused local_contract/verify；同步形成新 commit/parent 后按 daily REQ-003 重验最终候选 Alpha（即使 tree 相同），Beta 仍仅显式 opt-in；旧 bundle 不复用。批量交付先在获授权的现有汇总 lane 合成最终 C，再验收，不替其他 lane 合并或恢复远端 lane fallback。POST 只与 PRE 的同一 `published_sha` 比较 HEAD、ahead/behind、status 和 WIP，证明 lane 包含该 SHA；远端后来前移只报告需下一轮同步，不在本轮重新解析切换目标。

## 完成证据

current owner identity/claim ref、同步前后 HEAD、冻结的 `origin/dev1.0` exact SHA、ahead/behind、采用的 `ff-only` 或显式授权 merge、merge commit SHA（若有）、冲突处置、focused 验证命令与退出码、WIP 保留证据。仅本地同步完成，不代表 dev 发布、Alpha、准出或 main 合入；不推远端 lane。

## 失败与停止

布局不符、无 current owner、fetch/远端 ref 不可用、进行中操作、claim/脏路径重叠、分叉未获 merge 授权、冲突无法保留双方语义或验证失败时 `GATE_BLOCK`。保留首个 typed blocker 与当前 Git 状态，不 reset/stash/clean/`--abort` 他人字节，不用 `-X ours/theirs` 整体覆盖，不把未验证 merge 冒充完成。

## 条件性交接

用户明确要求提交时交 `commit`；要求合入 dev 时交 integration 工作区的 `integrate-lane-to-dev`，不在本 lane 代跑或 `cd` 到其他 worktree。Skill 切换不增加提交、发布或环境授权。持久交接语义见 continue Skill。
