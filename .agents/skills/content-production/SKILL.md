---
name: content-production
description: Run or resume the canonical nine-stage Data producer workflow from frozen demand to an immutable release handoff.
metadata:
  kind: workflow
---

# content-production

本 Skill 是 Data 内容生产 producer 九阶段的唯一流程真相源。宿主 AI 直接读取冻结上下文、选择来源与素材、写业务产物、自检、独立 review，并显式决定 `pass|blocked`、typed issues、approved 对象、release cohort 与 milestone；仓库代码不选择来源、不创作、不评审、不推进阶段，也不派生业务结论。

固定顺序只有：

```text
0.plan -> sources -> 1.download -> 2.quality -> 3.compose -> 4.draft -> 5.review
-> publish -> release -> END
```

`release` 业务 pass 先 create-once 关闭 sequence 009 receipt；随后 `release handoff` 只读该 receipt 与 release/cohort/pool/baseline facts，create-once 物化 immutable handoff，producer 才固定到 `END`。环境 import/activate/readback、环境 health、App/API UAT、`EnvironmentAcceptanceFact`（EAF）以及 promotion/rollback/replay 属于下游环境 owner 的并行 workflow；它们不是本 Skill 的阶段、receipt、恢复条件或完成条件。本 Skill 不删除也不禁止下游使用既有 `ship` CLI，只是不拥有它。

每次只加载当前 `references/stage-contracts/<stage>.md`、[handoff-protocol.md](references/handoff-protocol.md) 与必要载体差异。宿主可用原生会话串行执行，也可并发处理不同 execution/对象；批量并发、限流、reviewer session 派发、重启与排队全部属于宿主 runtime，不写入仓内状态。

## 触发与输入

本轮若产生、更新或恢复送审交付件 `content-release`，PRE 必须从 current execution/release owner facts 唯一解析 repository-relative exact target；缺失、多 owner 或漂移时 typed `GATE_BLOCK`。随后运行 `make feature-context TARGET=<exact-path>`，保存 content-addressed immutable owner manifest exact ref，PRE 后不得替换。纯只读且无送审交付只允许 `report-only/no-review-deliverable`。

Review 交互只引用 `quwoquan_ops/policies/human_agent_delivery_contract.yaml#workflow_interaction_binding.bindings.content-production`，由 canonical projector 生成可见输出；准出 deliverable 与 registry 名称保持为 `content-release`。

1. 新任务只允许用 `python3 quwoquan_data/scripts/cli.py task init --carrier-demand <path> --candidate-bindings <path>` 原子创建工作包；命令只写 `execution_manifest.json`、`0.plan/request.json`、`0.plan/target_set.json`。
2. 已有 execution 只读 producer create-once receipts 判断：最后一份 `pass` receipt 后进入本 Skill 固定的后继；`release` pass 后只交 immutable handoff 并结束。最后一份 `blocked` receipt 必须创建新 execution，从 `0.plan` 重来；某阶段已有 OPEN 而无 CLOSE 时，在同一冻结输入上重做该阶段。
3. 调用 `task stage-open --execution-id <id> --stage <stage> --input <stage-open-input.json>`，由 AI 在 `inputRefs[]` 精确点名本阶段全部输入；内核只检查路径/摘要/schema 并冻结 exact bytes。缺失、跨 execution 或摘要漂移即 blocked。
4. 禁止读取或调用 stage-gate registry、semantic prepare/record wrapper、runner/fleet/lane claim、自动恢复、execution state reducer、managed provider/SDK 或旧 sequence-017。

## 执行

宿主 AI 严格按当前阶段契约直接工作：只读 OPEN 冻结输入，作出语义选择，逐对象写业务产物。AI 负责来源选择、质量判断、compose、homepage/article 正文、image caption/work、`video_script`、逐对象 self-check、独立 review、verdict/typed issues、approved 对象，以及 explicit cohort/milestone。

代码只可承担 `task init`、stage-open/close、atomic download/CAS、schema/digest/ref/media hard facts、`publish-object` 与显式 cohort `pool-build`。不得让脚本合成正文、caption、video script、review、typed issue、verdict、approved 对象、cohort、milestone、后继或恢复动作；不得建立第二份流程文档、中央 registry、processor、queue 或状态机。

## 完成证据

1. 宿主逐条运行当前 stage contract 点名且当前真实存在的机械 verifier；不得用组合 registry 代跑。verifier 只验证 schema、引用闭包、摘要、媒体硬事实与原子 I/O 结果，不作业务语义判断。
2. 宿主读取真实 verifier 结果并完成 AI self-check，形成 `actor`、`verdict=pass|blocked`、`typedIssues[]`、`resultRefs[]`、`verifierFacts[]`。不得伪造退出码、来源、权利、review 或 release 证据。
3. 调用 `task stage-close --execution-id <id> --stage <stage> --input <agent-result.json>`。内核只重验 OPEN exact bytes、结果 schema、verifier facts 与 result refs，然后 create-once 写 receipt；内核不派生 verdict、typed issues 或后继。`release` CLOSE 的 resultRefs 必须绑定当前 release header/payload 事实；receipt 创建后才允许 `release handoff` terminal materialization，避免 digest 循环。
4. `pass` 的后继只查本 Skill 固定顺序；`blocked` 不在原 execution rewind，必须创建新 execution。
5. 显式或准出 Review 必须把 PRE 保存并在 POST 原样复用的 ref 作为 `--context-manifest` 传入；缺 ref、摘要漂移或 required evidence 未完成均不得声称 `content-release` 完成。

产生 `content-release` 时，POST 必须把 PRE owner identity ref 原样作为 `--owner-identity`，并把 current candidate evidence ref 作为 `--candidate-evidence` 传给 Review（workflow=`content-production`、segment=`POST`、deliverable=`content-release`、scope=`<exact-path>`）；先按 plan 去重执行命名 evidence，再派 registry 主审与至多一名专审。manifest ref 缺失、与 PRE 不同或 stale，required evidence/Reviewer 未完成，均不得完成。

内容生产完成证据只包括九阶段连续 create-once receipt 链，以及 `release` HANDOFF 要求的 immutable facts；下游环境 owner 可并行消费 handoff，但环境结果不得回授、覆盖或重开 producer terminal。

## 失败与停止

任一输入、producer receipt、引用摘要、owner manifest 或 release handoff 必填事实不闭合即停止并报告首个 typed blocker；不得手改门禁、伪造证据、回写旧 receipt 或绕过新 execution 重试规则。

未闭合项必须明确报告为未完成。不得用环境成功、旧 proof、sequence-017、fixture、counts 或历史 receipt 代替当前 producer/release 证据；也不得因下游环境尚未运行而把已经闭合的 release handoff 改写为 producer 失败。

## 条件性交接

普通阶段 HANDOFF 只报告 receipt ref/digest、业务 result refs、typed issues，以及本 Skill 固定后继。`release` CLOSE 后由统一 CLI create-once 物化 HANDOFF，交付 release ref/digest、producer release receipt ref/digest、explicit cohort ref/digest、milestone、四载体 counts（含 total）、逐对象 content-pool query identity/digest 与 producer baseline revision，然后固定到 `END`；下游环境 owner 只读这些 immutable facts。

源码/spec mutation 只交 Feature workflow；跨宿主接手、下游环境消费、外部阻断或证据复用满足 canonical 触发时生成 handoff。送审交付的 handoff 必须携带 PRE owner identity ref 与 POST candidate evidence predecessor；纯只读无送审交付不生成替代 manifest。
