---
name: content-production
description: Run the canonical ten-stage Data content workflow from frozen demand to immutable release and target delivery evidence, or continue an execution from create-once receipts.
metadata:
  kind: workflow
---

# content-production

本 Skill 是 Data 内容生产十阶段的唯一业务工作说明。宿主 AI 直接读取上下文、选择来源、写业务产物、自检并决定 `pass|blocked` 与 typed issues；仓库代码不选择来源、不创作、不评审、不推进阶段，也不派生业务结论。

固定顺序只有：

```text
0.plan -> sources -> 1.download -> 2.quality -> 3.compose -> 4.draft -> 5.review
-> publish -> release -> ship -> END
```

每次只加载当前 `references/stage-contracts/<stage>.md`、[handoff-protocol.md](references/handoff-protocol.md) 与必要载体差异。宿主可用原生会话串行执行，也可让彼此独立的宿主会话并发处理不同 execution；跨会话只依赖磁盘业务产物与 create-once receipt，不依赖聊天记忆或仓内调度器。

## 触发与输入

本轮若产生、更新或恢复送审交付件 `content-release`，PRE 必须从 current execution/release owner facts 唯一解析 repository-relative exact target；缺失、多 owner 或漂移时 typed `GATE_BLOCK`。随后运行 `make feature-context TARGET=<exact-path>`，保存 content-addressed immutable owner manifest exact ref，PRE 后不得替换。纯只读且无送审交付只允许 `report-only/no-review-deliverable`。

Review 交互只引用 `quwoquan_ops/policies/human_agent_delivery_contract.yaml#workflow_interaction_binding.bindings.content-production`，由 canonical projector 生成可见输出；准出 deliverable 与 registry 名称保持为 `content-release`。

1. 新任务只允许用 `python3 quwoquan_data/scripts/cli.py task init --carrier-demand <path> --candidate-bindings <path>` 原子创建工作包；命令只写 `execution_manifest.json`、`0.plan/request.json`、`0.plan/target_set.json`。
2. 已有 execution 只读 create-once receipts 判断：最后一份 `pass` receipt 后进入本 Skill 固定的下一阶段；最后一份 `blocked` receipt 必须创建新 execution，从 `0.plan` 重来；某阶段已有 OPEN 而无 CLOSE 时，在同一冻结输入上重做该阶段。
3. 调用 `task stage-open --execution-id <id> --stage <stage> --input <stage-open-input.json>`，由宿主在 JSON 的 `inputRefs[]` 显式提交本阶段全部 input refs；内核只做路径/摘要/schema 检查并冻结 exact bytes。缺失、跨 execution 或摘要漂移即 blocked。
4. 禁止读取或调用 stage-gate registry、semantic prepare/record wrapper、runner/fleet/lane claim、自动恢复、execution state reducer、managed provider/SDK 或旧 sequence-017。

## 执行

宿主 AI 严格按当前阶段契约直接工作：读 OPEN 冻结输入，作出语义选择，逐对象写业务产物。来源选择、事实取舍、正文或 video script、review 判断、发布 cohort 与环境动作都由宿主 AI 显式决定。代码只可承担下载/CAS、schema 与硬事实 verify，以及单对象 publish、immutable release、ship 的原子 IO。

不得让脚本合成正文、review、typed issue、verdict、下一阶段或恢复动作；不得建立第二份流程文档、中央 registry、processor、queue 或状态机。

## 完成证据

1. 宿主逐条运行当前阶段契约点名的 verifier；不得用组合 registry 代跑。verifier 只验证 schema、引用闭包、摘要、媒体硬事实与原子 IO 结果，不作业务语义判断。
2. 宿主读取每条 verifier 的真实结果，自检业务产物，形成 `actor`、`verdict=pass|blocked`、`typedIssues[]`、`resultRefs[]`、`verifierFacts[]`。不得伪造退出码、来源、权利、review、release、环境或 UAT 证据。
3. 调用 `task stage-close --execution-id <id> --stage <stage> --input <agent-result.json>` 提交上述结构化结果。内核只重验 OPEN 的 exact bytes、结果 schema、显式 verifier facts 与 result refs，然后 create-once 写 receipt；内核不派生 verdict、typed issues 或 next。
4. `pass` 的下一阶段只查本 Skill 固定顺序；`blocked` 不在原 execution rewind，必须创建新的 execution。
5. 显式或准出 Review 必须把 PRE 保存并在 POST 原样复用的 ref 作为 `--context-manifest` 传入；缺 ref、摘要漂移或 required evidence 未完成均不得声称 `content-release` 完成。

产生 `content-release` 时，POST 必须把 PRE owner identity ref 原样作为 `--owner-identity`，并把 current candidate evidence ref 作为 `--candidate-evidence` 传给 Review（workflow=`content-production`、segment=`POST`、deliverable=`content-release`、scope=`<exact-path>`）；先按 plan 去重执行命名 evidence，再派 registry 主审与至多一名专审。manifest ref 缺失、与 PRE 不同或 stale，required evidence/Reviewer 未完成，均不得完成。

Data 内容交付完成证据必须同时包含：十阶段 create-once receipt 链、immutable release exact identity、目标环境 ship apply/import/readback/health exact refs，以及本次内容验收要求的 API consumer raw `ReadinessCaseResult` refs。上述内容是 Data ship 的交付证据；Data 不创建、补写或把 `EnvironmentAcceptanceFact` 作为本 Skill 的 terminal writer 结果。

`m1_api_consumer` 仅可保留为内容 execution 选择 API consumer CaseResult 的 intent；它不是 EAF profile、EAF 字段或独立 writer。若下游要求 EAF，HANDOFF 必须把同一 exact integration candidate 的 Environment Ops scheduler request 与 current CaseResult refs 交给 Environment Ops；scheduler 只使用 canonical `profile=smoke|integration|release`，并在 `candidate`、`impactPlanDigest`、`caseResultRefs`、`runtimeIdentity`、`dataLifecycle`、`providerReadiness`、`observabilityReadiness`、`inspectEvidence`、`doctorEvidence`、`cleanupEvidence`、`leaseClosureEvidence`、`predecessor`、有效期、`nonPromotable` 与 DSSE signer 全部闭合后签发 EAF v2。不得从内容 intent 省略 named closure，也不得由 Data 调用 EAF writer。

## 失败与停止

任一输入、receipt、引用摘要、owner manifest 或环境证据不闭合即停止并报告首个 typed blocker；不得手改门禁、伪造证据、回写旧 receipt 或绕过新 execution 重试规则。

未闭合项必须明确报告为未完成。不得用 release-only verify、旧 proof、sequence-017、fixture、counts 或历史 receipt 代替当前环境证据。

## 条件性交接

阶段 HANDOFF 只报告 receipt ref/digest、业务 result refs、typed issues，以及本 Skill 固定的下一阶段；不得输出 execution-state、fleet/campaign 状态或自动恢复指令。

源码/spec mutation 只交 Feature workflow；跨宿主接手、环境/发布、外部阻断或证据复用满足 canonical 触发时生成 handoff。送审交付的 handoff 必须携带 PRE owner identity ref 与 POST candidate evidence predecessor；纯只读无送审交付不生成替代 manifest。
