---
name: integrate-lane-to-dev
description: Ship an accepted candidate to origin/dev1.0 with one command in the current lane worktree. Lane resync after publish is an optional report, not a success gate. Use for 合入 dev1.0、集成到开发分支、发布 dev。
metadata:
  published_baseline: origin/dev1.0 frozen after fetch
  kind: workflow
  command: /integrate-lane-to-dev
---

# integrate-lane-to-dev

## 触发与输入

方向固定为 accepted candidate/bundle → `origin/dev1.0`。默认在产出 candidate 的当前规范 lane 工作树执行一条命令；消费他树 bundle 时使用唯一 `integration/` 工作区的等价两段形态，同一 candidate 只允许一个 publisher。输入为已提交 candidate、同候选 acceptance bundle（如采用 bundle 形态）、fetch 后冻结的 published parent、状态与发布授权；无验真 admission 不动远端 dev，不消费未发布 dev 或远端 lane/PR。本通道只证明 source-admitted，不把 UAT、Data 激活、Gamma、容量写成发布资格。

## 执行

1. PRE 校验当前工作树是政策声明的规范 lane 或唯一 `integration/`，共享同一 bare hub origin，无进行中 Git 操作，HEAD 是 exact candidate；确定 exact target，运行 `make feature-context TARGET=<exact-path>` 取得 current context/owner identity，核 scope/claim。`git fetch origin` 后只解析一次 `refs/remotes/origin/dev1.0^{commit}` 为 `published_sha`，记录 HEAD/candidate/ahead-behind/status；解析失败不回落本地 dev。
2. 发布前验证 candidate/bundle 与 parent：bundle 形态运行 `make integrate CANDIDATE=<exact-candidate-sha> ACCEPTANCE_BUNDLE=… PUBLISH=0 INTEGRATE_ARGS=--validate-bundle-only`，覆盖 bundle 摘要/签名/有效期、commit/tree、完整 scope、required Review、typed Alpha/Beta 前驱及 `candidate.parent == published_sha`；lane 直发形态运行等价的 acceptance/admission 校验。验证模式禁止 publish/import/admit/移动 HEAD，脏文件只在与 `expectedParent...candidate` 的发布 diff 重叠时阻断（本树 HEAD 即 candidate 时也不能用空 range 跳过检查），非重叠 WIP 零写保留；输入或远端漂移即 stale。
3. 验证通过后，lane 形态运行 `make accept PUBLISH=1`；bundle 形态由 integration 执行 `git merge --ff-only <exact-candidate-sha>` 后 `make integrate ... PUBLISH=1`。正式入口重验 bundle/remote parent，publish 只能 expected-old non-force FF，按 `before|after|other` 精确读回，仅 exact `after` 算成功；禁止裸 push、盲重试或整树覆盖。
4. 仅 readback 为 `after` 后本次合入完成；`make lane-resync-execute` 仅作可选报告，`skipped_*` 不是发布失败。其他 lane 在自己提交前按 `sync-lane-from-dev` / commit Skill 对齐已发布 SHA；分叉 merge 只能由该 lane 获明确授权后走同步 Skill。

## 完成证据

报告 current owner/claim ref、冻结 parent、candidate/bundle、dev 前后 HEAD、accept/integrate summary 阶段与耗时、source/typed Alpha/Beta refs 或首个 typed blocker、publish `before|after|other` 读回与远端 exact SHA。源码合入与环境观察分层：UAT、Data 激活、Gamma、容量未跑或失败不否定本次合入，也不把 dev 发布称为 main 合入。

## 失败与停止

非规范 worktree / 非 hub origin、无 current owner、未提交 candidate、fetch/ref 失败、bundle 缺失/无效/stale、parent 漂移、non-FF、dirty overlap、required 闭集失败、readback 非 `after` 或发布拒绝均 `GATE_BLOCK`。保留首个 blocker、summary 与 WIP；不 reset/stash/clean/裸推。

## 条件性交接

成功 publish 才能作为 Gamma → `IntegrationQualificationFact` → `dev1.0 → main` promotion 前驱，交 `environment-ops`/release；main 后只走 managed backsync/readback/lane FF。不得 direct push main 或扩大到环境、PR merge、生产及外部写授权。持久语义见 continue Skill。
