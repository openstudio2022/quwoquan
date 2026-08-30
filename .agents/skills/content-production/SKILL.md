---
name: content-production
description: Run the canonical quwoquan data content workflow from reusable inputs through one execution work package, immutable release, environment import, and App UAT, and diagnose or resume a failed execution. Make sure to use this skill whenever the user mentions 按区域生成主页, 跑内容任务, 内容生产, 生产内容并导入环境, 复核 execution, 恢复内容任务, 重试实体任务, immutable release, or 数据发布, even without an explicit command.
metadata:
  kind: workflow
---

# content-production

## 触发与输入

在按区域生成主页、内容生产、复核或恢复 execution、重试实体任务、生成
immutable release、导入环境或数据发布时使用。

开始前取得：

- 区域、载体、生成家族等可复用运行输入；用
  `python3 quwoquan_data/scripts/cli.py verify runtime-input-ownership` 确认归属。
- 来源素材与 execution id；用 `verify source-digest --execution-id <id>` 冻结 CAS 摘要。
- 续跑时已有 receipt 链与 `execution_state.json`，二者只读消费；仅此场景读取
  [recovery.md](references/recovery.md)。

宿主 Agent 是调研、创作、决策和修正产物的唯一执行主体；脚本只做确定性 IO、
verify、原子 publish/release/ship 与 receipt 记录，不驱动或等待 Agent。工作包布局需要
定位时读取 [execution-layout.md](references/execution-layout.md)，不预载全部阶段文档。



自然语言触发与显式 Skill 调用同轨，字段、闭集与审计隔离只引用 `quwoquan_ops/policies/human_agent_delivery_contract.yaml#workflow_interaction_binding.content-production`：

- PRE：`progress_update` / `delivery_planning_authorization` / `engineering_delivery_owner`。

## 执行

所有子命令以 `python3 quwoquan_data/scripts/cli.py` 为入口，并只从磁盘 owner facts 进入同一阶段链：

1. 新任务先确认 confirmed demand 与 immutable candidate binding。唯一初始化命令是中性 `task init --carrier-demand <path> --candidate-bindings <path>`，它只原子物化 `execution_manifest.json`、`0.plan/request.json`、`0.plan/target_set.json`，零 stage 副作用；输入必须是 confirmed carrier demand 与 immutable candidate bindings，不得改用 `task execute`（含 plan-only）、pool-dispatch/campaign 或手写工作包。
2. 宿主 Agent 不运行仓内 semantic provider、Cursor key/model、SDK、capacity 或 workspace soak preflight。进入每个 stage 时只执行该 stage 契约声明的 deterministic input/layout/source/rights/runtime PRE。
3. M100 gap 与 candidate readiness 只能经只读 pool handoff query/precheck 查看；query 不得写 selection、冻结 slot 或启动 production。M1000 在同一 M100 exact release 完成必要前序、Gamma import/readback、registered physical-device raw App UAT 与 Gamma acceptance 前保持生产副作用为 0；gate 后本轮首 slot 只到 `0.plan pass -> next=sources`。
4. 续跑或跨宿主接手按 [recovery.md](references/recovery.md) 的 receipt 判定表定位唯一断点。
5. loop、并发或 fleet 才读取 [orchestration.md](references/orchestration.md)；两个 runner 只起收宿主进程、只读 receipt，不含 candidate 选择、业务重试或旧 `agent/queue/controller/recovery/campaign` 入口。

只在进入某阶段时读取对应契约，并按顺序推进：

| 阶段 | 按需契约 | 完成证据 |
| --- | --- | --- |
| `0.plan` | [0.plan.md](references/stage-contracts/0.plan.md) | `verify runtime-input-ownership`、`verify content-execution-layout` |
| `sources` | [sources.md](references/stage-contracts/sources.md) | `verify source-digest --execution-id <id>` |
| `1.download` | [1.download.md](references/stage-contracts/1.download.md) | 契约中当前 lane 的命名证据 |
| `2.quality` | [2.quality.md](references/stage-contracts/2.quality.md) | `verify stage-artifacts --execution-id <id>` |
| `3.compose` | [3.compose.md](references/stage-contracts/3.compose.md) | `verify stage-artifacts --execution-id <id>` |
| `4.draft` | [4.draft.md](references/stage-contracts/4.draft.md) | 契约中当前 lane 的命名证据 |
| `5.review` | [5.review.md](references/stage-contracts/5.review.md) | `verify rubric --file <path> --generation-family <family>` |
| `publish` | [publish.md](references/stage-contracts/publish.md) | `verify publish-purity`、`verify publish-closure` |
| `release` | [release.md](references/stage-contracts/release.md) | `verify release-integrity --release <path>`、`verify media-release-contract` |
| `ship` | [ship.md](references/stage-contracts/ship.md) | `verify release-lifecycle`、`stackctl verify --env gamma`、App UAT |

每阶段只由 `task stage-record` 创建一次 receipt。载体差异仅在处理对应载体时读取
[carriers/](references/carriers/)；阶段失败才读取 [self-repair.md](references/self-repair.md)，
修复产物后重跑同一命名证据，不跳阶段。

- 执行中：`exception_escalation` / `nonproduction_validation` / `$route`。

`$route` 表示按当前决定责任动态路由；Skill 不复制 envelope schema，所有可见输出统一由 canonical projector 生成。

## 完成证据

完成必须同时绑定同一 execution 的 receipt 链、immutable release、环境 import/readback
和 App UAT，不以某个上游 PASS 代替下游闭环。报告至少引用：

- `.qwq_output/data/tasks/<executionId>/_shared/receipts/`
- `.qwq_output/data/releases/<releaseId>/`
- `.qwq_output/env/<env>/runs/data-release/<releaseId>/<runId>/`

publish/release 的 POST Review 先由主会话按 Review registry 解析并执行一次去重的命名
evidence，再调用 `review`（workflow=`content-production`、segment=`POST`、
deliverable=`content-release`）。主审是 `data-quality`；命中内容发布 profile 时至多增加
一个 `data-legal` 专审。Reviewer 只裁决已有证据，不自行运行 gate。required evidence 或
required Reviewer 未完成即返回 typed `GATE_BLOCK`。

- POST：`completion_report` / `nonproduction_validation` / `$route`。

## 失败与停止

- 禁止手改 verify/schema/门禁参数，禁止手写 receipt 或 `execution_state.json`。
- 禁止补造 source、rights、review、release、import/readback 或 UAT 证据；缺失时携带
  `executionId` 和首个失败阶段返回 `GATE_BLOCK`。
- receipt 链、source digest、release identity 或环境读回不一致时停止，由 recovery 判定表
  决定返回阶段；不得从后续阶段反向修饰旧证据。
- 宿主 Cursor/Codex 凭证与模型能力由宿主自身管理；Data 仓库、工作包、日志与 receipt 不读取、不保存 key、token、片段或指纹。

## 条件性交接

六类触发（跨会话未完成、多人并行、环境/发布、外部阻断、证据复用、用户显式要求）统一调用 canonical handoff producer；普通闭环不落持久交接。

仅当路由结果要求真实人类责任时，使用统一 `$route`、project/card 与 hosted authority readback；routine execution 不新造 checkpoint。Reviewer PASS 只是评审证据，不能签发或替代 authority receipt。
