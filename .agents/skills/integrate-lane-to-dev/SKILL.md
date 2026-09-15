---
name: integrate-lane-to-dev
description: Validate the exact accepted candidate before integration FF/publish; sync local lanes only after published readback. Use when the user says 合入 dev1.0, 集成到开发分支, 发布 dev, 同步到各个工作树, or 回同步各 lane.
metadata:
  published_baseline: origin/dev1.0 frozen after fetch
  kind: workflow
  command: /integrate-lane-to-dev
---

# integrate-lane-to-dev

## 触发与输入

方向：已验 exact candidate/bundle → `origin/dev1.0` → 六条本地 lane。仅唯一 `integration/` 工作区执行，lane 触发时提示切换、不代跑。输入：candidate SHA、同一候选 `ACCEPTANCE_BUNDLE`、fetch 后冻结的 published parent、本地 dev/各 lane 状态与明确发布授权。分支/布局只读 `branch_policy.yaml#integration_branch` 与 `worktree_policy.yaml`；发布与重验语义归 `daily-merge-release-strategy` REQ-002/003。无有效 bundle 不移动本地/远端 dev，不消费未发布本地 dev，不依赖远端 lane/PR。

## 执行

1. PRE 校验 HEAD 为 `dev1.0`、工作区为 integration、无进行中 Git 操作；确定 exact target，运行 `make feature-context TARGET=<exact-path>` 获唯一 current owner identity ref，并核对 exact scope/活跃 claim。`git fetch origin` 成功后仅一次用 `git rev-parse --verify refs/remotes/origin/dev1.0^{commit}` 冻结 `published_sha`，记录本地 HEAD、candidate SHA、ahead/behind、status；fetch/远端解析失败即阻断，绝不 fallback 本地 dev。
2. **本地 dev 移动前验证 bundle/parent**：执行现有 `make integrate CANDIDATE=<exact-candidate-sha> ACCEPTANCE_BUNDLE=… PUBLISH=0 INTEGRATE_ARGS=--validate-bundle-only`。预检与正式 admission 共用纯验真：exact bundle 摘要、签名/有效期、candidate commit/tree、完整 scope/full required/Review 与 Alpha/Beta 前驱；fast-only、deferred、no_live 无 Alpha 均在 HEAD 移动前拒绝。要求终态 `bundle_validated` 且 summary 的 `candidate.parent` 等于 PRE 冻结的 `published_sha`。该模式要求 exact SHA、禁止 `--publish`，不 import/admit、不移动 HEAD；其间远端变化即 stale。再证明本地 dev 可 FF 到该 candidate，工作树符合当前编排的干净要求且 untracked 不重叠。缺 bundle、stale 或验证失败必须 HEAD/index/WIP 零变化，不默认清理；不得先 FF 再检查 bundle。
3. 验证通过后执行 `git merge --ff-only <exact-candidate-sha>` 并读回 HEAD 等于该 SHA，再调用 `make integrate CANDIDATE=<exact-candidate-sha> ACCEPTANCE_BUNDLE=… PUBLISH=0` 正式 import/admit；只有明确发布授权时将 `PUBLISH` 设为 `1`，且不再传 `--validate-bundle-only`。正式入口要求 HEAD 已等于 candidate，并重新验证 bundle/远端 parent，预检不能替代发布前复核。完整输入未变的单 lane 原样 FF 不重跑 Alpha/Beta；多 lane 必须先在现有汇总 lane 合成最终 C 再 Alpha，Beta 全链仅显式 opt-in、不将 not_required 当 passed。integration 不 merge/修源码；新 commit/parent 或冲突退回汇总 lane 重验。发布按 expected-old non-force FF 并以 `before|after|other` readback 判定；只有 `after` 且等于 exact candidate 才有 publish result。禁止裸 push；读回 `before`/`other` 不盲重试。只 admit 未 publish 不触发回同步。
4. **仅 readback 为 after 后**，重新 `git fetch origin`，执行 `make lane-resync-execute`：该批次只解析一次已发布 `origin/dev1.0` exact SHA，所有 lane 的判定、执行与结果共享这个冻结目标，不重新解析各 lane 的本地 dev。只对无进行中操作、脏路径与 ff 不重叠且 HEAD 为目标祖先的 lane 做本地 FF；不推同名远端、不默认清理。`skipped_missing` / `skipped_in_progress` / `skipped_dirty_overlap` / `skipped_diverged` 保持该 lane 零写并交回其会话；`ff_failed` 保留真实状态。batch 绝不 merge 分叉，由当前 lane 经明确授权调用 `sync-lane-from-dev`。

## 完成证据

current owner identity/claim ref、PRE 冻结的 `origin/dev1.0` parent SHA、exact candidate/bundle、本地 dev 前后 HEAD、`make integrate` summary 与各阶段状态/耗时（含 `reused`）、source/Alpha/Beta refs 或首个 typed blocker、publish result 与 `before|after|other` readback、回同步批次冻结的 published SHA 及每条 lane 的结果 JSON。源码、readiness、Alpha、发布与本地回同步分层报告；不把 dev 发布称为 main 合入。

## 失败与停止

非 integration、无 current owner、fetch/远端解析失败、缺 bundle、无效/stale bundle、parent 漂移、本地 non-FF 或脏重叠、事实验证失败、readback 非 `after` 或发布拒绝时 `GATE_BLOCK`。保留首个 typed blocker、真实 summary 与 WIP，不用旧 receipt、不 reset/stash/clean、不裸推，也不因部分 lane 成功而掩盖跳过/失败。

## 条件性交接

仅 publish result 可作为 current published dev 的 Gamma → `IntegrationQualificationFact` → `dev1.0 → main` promotion PR 的前驱，交现有 `environment-ops` / release 流程；main merge 后沿现有受管 backsync、readback 与本地 lane FF 流程继续。不得 direct push main，不把“合入 dev”扩大为 Gamma 执行、PR 创建/merge、生产发布或外部写入授权。被跳过 lane 交其自身 `sync-lane-from-dev`；持久交接语义见 continue Skill。
