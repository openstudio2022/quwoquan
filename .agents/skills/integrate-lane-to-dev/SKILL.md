---
name: integrate-lane-to-dev
description: In integration, fast-forward dev1.0 to a lane head, publish source-only when authorized or consume a lane acceptance bundle, then read back and ff-only resync eligible lanes. Use when the user says 合入 dev1.0, 集成到开发分支, 发布 dev, 同步到各个工作树, or 回同步各 lane.
metadata:
  kind: workflow
  command: /integrate-lane-to-dev
---

# integrate-lane-to-dev

## 触发与输入

把某条 lane head 合入开发集成分支并回同步各 lane，方向固定 lane → dev → 其余 lane；开发分支默认取 `branch_policy.yaml#integration_branch`（当前 `dev1.0`，下文以此指代），用户显式指定时以用户为准，Skill 名不绑定版本。只能在唯一 `integration/` 工作区执行，lane 工作区触发时提示切换而不代跑。输入：目标 lane 或 exact lane head、本地/远端 `dev1.0` 头、各 lane 工作树状态、用户授权范围；带资格通道另需 `ACCEPTANCE_BUNDLE`，仅源码通道不要求 Data release 或资格事实。通道与回同步语义只读 `branch_policy.yaml`，布局只读 `worktree_policy.yaml`，发布语义归 `daily-merge-release-strategy` REQ-002，本 Skill 不复述。

## 执行

1. PRE 校验 HEAD 为 `dev1.0`、工作区为 integration 目录、无进行中 merge/rebase；`git fetch origin` 并记录本地/远端 `dev1.0` 与目标 lane 的 SHA 与 ahead/behind。要求 `dev1.0` 是目标 lane 的祖先；否则停止并交该 lane 会话先运行 `sync-lane-from-dev`，不在 integration 里 merge lane。
2. `git merge --ff-only <lane>`，读回 HEAD 等于 lane head。
3. 按用户授权选择通道：仅源码合入不调用 `make integrate`，仍满足当前 hook、required check 与用户要求的候选验证；带资格合入只消费 lane 在同一 exact head 上 `make accept` 产出的 bundle，执行 `make integrate ACCEPTANCE_BUNDLE=…`。Alpha 在 lane 完成，Beta 仅 `BETA=1`；integration 不补跑 Alpha/Beta，Gamma 与生产独立后置。
4. 发布：带资格通道以 `PUBLISH=1` 按 expected-old fast-forward 发布并按 `before|after|other` 读回，只有 `after` 写 publish result；用户已明确授权仅源码时直接 `git push origin refs/heads/dev1.0:refs/heads/dev1.0`，pre-push 校验 non-force fast-forward，不签发任何资格。两条通道都核对远端等于 exact candidate；读回 `before`/`other` 不盲重试。
5. 回同步：`make lane-resync-execute`，只对「无进行中 merge、干净或脏文件与 ff 不重叠、且是新 `dev1.0` 祖先」的 lane 执行 `merge --ff-only` 并推送同名远端；其余 lane 只记录 `skipped_in_progress` / `skipped_dirty_overlap` / `skipped_diverged` / `push_failed`，由该 lane 会话自行运行 `sync-lane-from-dev`。不在其他工作树里 merge、覆盖或清理任何字节。

## 完成证据

目标 lane 与 `dev1.0` 前后 SHA、`make integrate` summary 路径与各阶段状态/耗时（含 `reused`）、Alpha/Beta 事实 ref 或首个 typed blocker、publish 通道与 `before|after|other` 读回、每条 lane 的回同步结果 JSON。源码推送、readiness、Alpha 事实与回同步四层分开报告；裸 push 明确标注「仅源码，无资格」。

## 失败与停止

不在 integration 工作区、`dev1.0` 不是 lane 祖先、ff 失败、readiness 或 Alpha 失败且用户未授权裸推、读回 `before`/`other`、pre-push 拒绝、任一 lane 推送失败时 `GATE_BLOCK`：保留首个 typed blocker 与真实 summary，不用旧 receipt 冒充当前 candidate，不因部分 lane 已回同步而把整体包装为成功。

## 条件性交接

仅带资格通道的 publish result 可作为 current dev head Gamma 与 `IntegrationQualificationFact` 的前驱；普通源码 push 不产生该事实，后续资格链须独立补齐。交 `environment-ops` 或 release 流程消费；被跳过的 lane 交回其会话的 `sync-lane-from-dev`。持久交接语义见 continue Skill。
