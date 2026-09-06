# Data 内容生产职责边界

| 主体 | 允许 | 禁止 |
| --- | --- | --- |
| 宿主 Cursor/Codex Agent | 唯一语义主体；读冻结上下文、点名 exact input refs、选择来源与素材、写单一 draft/review 产物、自检、决定 pass/blocked/typed issues、approved 对象、explicit cohort/milestone、按 Skill 固定顺序推进 | 伪造证据、放宽 schema/verifier、手写 receipt、修改已冻结输入或 immutable release |
| Skill | producer 九阶段唯一流程真相源、每阶段输入/输出、机械 verifier、AI self-check、固定后继与 release handoff | 复制 schema/代码常量、建立第二流程、registry、processor、模型/并发策略或状态机；把环境 workflow 纳入 producer 完成条件 |
| 代码内核 | identity-only `task init`、stage-open exact input freeze、stage-close create-once、atomic download/CAS、schema/digest/ref/media hard facts、单对象 `publish-object`、显式 cohort `pool-build` | 来源/选材/创作/review、verdict/issue/approved/cohort/milestone/后继派生、resolver/projector/runner/controller/queue/registry/SDK、自动恢复、actor projection |
| 下游 consumer/environment owner | 本 Skill 范围外；可只读 immutable release handoff 后独立执行消费 | 把 UAT/sample authority/import/activate/readback/EAF/promotion/rollback 写入 producer handoff，或改写 producer terminal |

硬约束：

1. 代码同步返回，不等待 AI 回写。
2. verifier 只验证可重复的硬事实，不作语义判断。
3. 一个 execution 的 `4.draft` 只有一个 author 会话，`5.review` 只有另一个 reviewer 会话；sequence-006/007 receipts 分别是 actor 真相源。
4. 每个 approved 对象独立原子 publish；一个对象失败不回滚其它已成功对象。
5. release 必须消费 AI 显式 cohort；M1/M10/M100/M1000 按累计唯一 finalized 对象计数，各级形成独立 cohort/release/handoff，复用原 proof。
6. release handoff 必须携带 release/cohort、executionIds/sequence-009 receipts、milestone、carrier counts、content-pool query、原 producer proof 与 baseline revision；不含 consumer/environment facts。
7. 每个 execution 的 `release` sequence-009/pass 后还必须 terminal handoff create-once 成功才到 `END`；producer receipt 与 handoff facts 是跨会话状态，无 shim、dual-read、legacy fallback 或 sequence-017 兼容。
