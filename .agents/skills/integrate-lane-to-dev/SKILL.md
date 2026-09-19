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

仅唯一 `integration/` 工作区执行：已验 candidate SHA、同候选 `ACCEPTANCE_BUNDLE`、fetch 后冻结的 published parent、状态与发布授权。方向为 candidate/bundle → `origin/dev1.0` → 本地 lanes。策略只读 `branch_policy.yaml`、`worktree_policy.yaml` 与 daily REQ-002/003。无有效 bundle 不移动 dev；不消费本地未发布 dev、远端 lane 或 PR。

## 执行

1. PRE 校验 `dev1.0`、integration 布局、无进行中 Git 操作；确定 exact target，非授权 `feature-context` 可 unresolved；核对 exact-path claim 与 actual diff/ImpactPlan。`git fetch origin` 后仅一次解析 `origin/dev1.0^{commit}` 为 `published_sha`，记录 HEAD/candidate/ahead-behind/status；失败不回退本地 dev。
2. HEAD 移动前运行 `make integrate CANDIDATE=<sha> ACCEPTANCE_BUNDLE=… PUBLISH=0 INTEGRATE_ARGS=--validate-bundle-only`。验证 exact bytes、签名/有效期、commit/tree、完整 scope、required Review、Alpha/Beta 前驱，且 `candidate.parent == published_sha`。该模式禁 publish/import/admit/移动 HEAD；远端变化即 stale。再证明可 FF、工作树满足干净要求且 untracked 不重叠；失败保持 HEAD/index/WIP。
3. 通过后 `git merge --ff-only <candidate>` 并读回，再执行不带 validate-only 的 `make integrate`；仅明确授权时 `PUBLISH=1`。正式入口重新验证 bundle/parent；integration 不改源码或 merge 冲突。发布只用 expected-old non-force FF，readback 仅 `after == candidate` 成功；禁止裸 push/盲重试。
4. 仅 publish readback `after` 后 fetch 并运行 `make lane-resync-execute`。批次共享一次冻结的 published SHA；仅对无进行中操作、脏路径不重叠、HEAD 为目标祖先的 lane 本地 FF，不推 lane、不清理。missing/in-progress/dirty/diverged 保持零写；分叉交各 lane 的 `sync-lane-from-dev`。

## 完成证据

报告 claim、published parent、candidate/bundle、dev 前后 HEAD、integrate summary、source/Alpha/Beta 或首个 blocker、publish readback、批次 SHA 与各 lane 结果；分层陈述，不称 main 合入。

## 失败与停止

报告 claim、published parent、candidate/bundle、dev 前后 HEAD、integrate summary、source/Alpha/Beta 或首个 blocker、publish readback、批次 SHA 与各 lane 结果；分层陈述，不称 main 合入。布局/fetch/bundle/parent/FF/脏重叠/事实/readback 任一失败即 `GATE_BLOCK`，保留 WIP，不用旧 receipt，不 reset/stash/clean/裸推。

## 条件性交接

仅已发布 dev 可交 Gamma → IQF → `dev1.0 -> main` PR；不得扩大为 Gamma、PR、生产或外部写授权。
