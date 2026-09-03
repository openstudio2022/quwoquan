---
name: continue
description: Resume and drive the development loop from wherever the session stopped - finish interrupted todos with their verification, or close a finished round via plan-next and enter the next one. Use when the user says 继续, 继续开发, 接着做, 续跑, 按规划实施, or 复盘后接着做, or when a session resumes after an interrupted todo run.
metadata:
  kind: workflow
  command: /continue
---

# continue

## 触发与输入

用于从中断位置续跑，或收口已完成轮次后进入下一轮。输入优先是当前 todo/plan、Git 字节、最近 immutable owner ref、证据与持久交接（如有），不以对话印象为证据。角色交互只引用 `quwoquan_ops/policies/human_agent_delivery_contract.yaml#workflow_interaction_binding.bindings.continue`，可见输出由 canonical projector 生成。

## 执行

1. 重建 HEAD/status、目标 diff、untracked、writer、plan/todo、证据 freshness 与 durable handoff。
2. 识别被恢复的原 Workflow Skill：未完 todo 继续原工作流，上轮已收口进入 plan-next，无可靠上下文先 explore。
3. 完整继承被恢复 Skill 的 PRE、target 解析、immutable owner ref、验证与 POST 规则；continue 不自建 manifest 前置、resolver、Reviewer 或证据逻辑。
4. 被恢复 workflow 是 plan-next、explore 等只读控制型 workflow 时，`feature-context` 失败按其 best-effort 语义记录 typed owner 解析结果并继续只读；被恢复 workflow 是 prd、design、dev 等 mutation workflow 时，进入写入前仍必须取得唯一 owner 与 immutable ref。
5. stale ref/receipt 由所属工作流按当前 target 重新生成或复跑，不转抄聊天记忆和旧摘要。

## 完成证据

报告采用的恢复分支、继承的 workflow、当前 exact target/ref、已恢复产物与证据、剩余 todo 和首个 typed blocker；完成判定以被恢复 Skill 为准。

## 失败与停止

恢复 workflow/target 不唯一、证据过期、持久交接断链，或 mutation workflow 写入前无法取得唯一 owner/ref 时 `GATE_BLOCK`，先 explore 或重建所属证据。发现并行冲突时报告风险与共享写点，只编辑本任务字节并交由准出暴露冲突；不扩大授权，也不 reset/clean/kill 推测恢复。

## 条件性交接

持久交接只认 producer 发布到 current git-common-dir authoritative store 后返回的显式 `handoff-ref-v1`；`.qwq_output` 仅为 projection/cache。恢复或准出必须显式传 ref，禁止扫描 latest、环境变量 truth 或依赖本机 clone/worktree inventory；跨 runner 传同一 ref+exact artifact bytes。

空 triggers 必须立即返回 `no_persistent_handoff`，不要求 artifact、Review 或 authority，也不创建 projection/store。六类 canonical trigger（`cross_session_incomplete`、`multi_party_parallel`、`environment_or_release`、`external_blocker`、`evidence_reuse`、`user_explicit_request`）任一成立都进入 owner/candidate/named evidence/Reviewer/consolidation 完整链和 authoritative create-once store；前两类也是正式 durable handoff，不是轻量 checkpoint。

当前没有 ordinary cross-session 轻量 checkpoint 的 canonical owner/schema；需要该能力时保持 OPEN，不临时创建第二状态源。Reviewer PASS 或当前 Human 聊天同意都不签发正式 authority；正式 provider 缺失继续 blocked/OPEN。
