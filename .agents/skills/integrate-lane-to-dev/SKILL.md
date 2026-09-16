---
name: integrate-lane-to-dev
description: Validate an accepted candidate before integration FF/publish, then sync local lanes from published readback. Use for 合入 dev1.0、集成到开发分支、发布 dev 或回同步各 lane。
metadata:
  published_baseline: origin/dev1.0 frozen after fetch
  kind: workflow
  command: /integrate-lane-to-dev
---

# integrate-lane-to-dev

## 触发与输入

方向固定为 accepted candidate/bundle → `origin/dev1.0` → 本地 lane，仅在唯一 `integration/` 工作区执行。输入为 candidate SHA、同候选 `ACCEPTANCE_BUNDLE`、fetch 后 published parent、状态与发布授权；分支/布局及发布重验只读 canonical policy 与 `daily-merge-release-strategy` REQ-002/003。无有效 bundle 不动本地/远端 dev，不消费未发布 dev 或远端 lane/PR。

## 执行

1. PRE 校验 HEAD=`dev1.0`、integration 布局及无进行中 Git 操作；确定 exact target，运行 `make feature-context TARGET=<exact-path>` 取得唯一 current owner identity ref，核 scope/claim。fetch 后只解析一次 `refs/remotes/origin/dev1.0^{commit}` 为 `published_sha`；记录 HEAD/candidate/ahead-behind/status。fetch/解析失败不回落本地 dev。
2. 移动 HEAD 前运行 `make integrate CANDIDATE=<sha> ACCEPTANCE_BUNDLE=… PUBLISH=0 INTEGRATE_ARGS=--validate-bundle-only`。纯验真必须覆盖 bundle 摘要/签名/有效期、commit/tree、完整 scope、required Review、Alpha/Beta 前驱，终态为 `bundle_validated` 且 parent=`published_sha`；该模式禁止 publish/import/admit/移动 HEAD。再证明可 FF 且 dirty/untracked 不重叠；输入或远端漂移即 stale，失败保持 HEAD/index/WIP 不变。
3. `git merge --ff-only <sha>` 后读回 exact HEAD，再执行正式 `make integrate ... PUBLISH=0|1`；仅明确授权可设 `PUBLISH=1`。正式入口重验 bundle/remote parent，integration 不修源码；新 parent/commit 或冲突退回汇总 lane重验。publish 只能 expected-old non-force FF，readback 仅 exact `after` 算成功；禁止裸 push，`before/other` 不盲重试。只 admit 不回同步。
4. 仅 `after` 后重新 fetch 并执行 `make lane-resync-execute`；整批只冻结一次已发布 SHA。仅安全祖先 lane 本地 FF，不推远端或清理；所有 skipped/failed 状态保持对应 lane 零写并交其会话。分叉 merge 只能由该 lane 获明确授权后走 `sync-lane-from-dev`。

## 完成证据

报告 current owner/claim ref、冻结 parent、candidate/bundle、dev 前后 HEAD、integrate summary/阶段/耗时、source/Alpha/Beta refs 或首个 typed blocker、publish `before|after|other` 读回、批次 published SHA 与各 lane 结果。源码/readiness/Alpha/发布/回同步分层，不把 dev 发布称为 main 合入。

## 失败与停止

非 integration、无 current owner、fetch/ref 失败、bundle 缺失/无效/stale、parent 漂移、non-FF、dirty overlap、事实失败、readback 非 `after` 或发布拒绝均 `GATE_BLOCK`。保留首个 blocker、summary 与 WIP；不 reset/stash/clean/裸推，不以部分 lane 成功掩盖失败。

## 条件性交接

成功 publish 才能作为 Gamma → IQF → `dev1.0 → main` promotion 前驱，交 `environment-ops`/release；main 后只走 managed backsync/readback/lane FF。不得 direct push main 或扩大到环境、PR merge、生产及外部写授权。被跳过 lane 交其 `sync-lane-from-dev`；持久语义见 continue Skill。
