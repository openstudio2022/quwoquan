# architect / distill

## POST

- [MUST] 每条候选的建议落点是唯一 owner，不与既有资产重复正文
  gate: make verify-agent-context-budget
- [MUST] 标 MUST 的候选绑定真实存在的 gate 命令或客观 check 谓词；无绑定候选只落 SHOULD/ADVISORY
  check: 候选清单中每条 MUST 候选的绑定命令在仓内可执行且退出码语义明确
- [MUST NOT] 本轮 diff 含未经用户确认的规则资产（AGENTS.md/SKILL.md/checklist/reference/gate）变更
  check: git diff 中规则资产改动均能对应候选清单里的「已确认」条目
- [SHOULD] 判为「一类」的候选写明系统性排查方式（全仓扫描 / gate 化 / 棘轮化）与防回潮锁
- [ADVISORY] 根因层判定偏向结构性修复：能 gate 化的不停留在 prompt 指令层

## HANDOFF

- 产出物：逐条候选的架构裁决（采纳 / 降级 / 拒绝）与理由
- 证据链：gate 输出与 check 核对结论
