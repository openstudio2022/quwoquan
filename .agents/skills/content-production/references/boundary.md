# Data 内容生产职责边界

| 主体 | 允许 | 禁止 |
| --- | --- | --- |
| 宿主 AI | 读冻结上下文、点名 exact input refs、选择来源与素材、写对象级产物、创作、自检、独立 review、决定 pass/blocked/typed issues、approved 对象、explicit cohort/milestone、按 Skill 固定顺序推进 | 伪造证据、放宽 schema/verifier、手写 receipt、修改已冻结输入或 immutable release |
| Skill | producer 九阶段唯一流程真相源、每阶段输入/输出、机械 verifier、AI self-check、固定后继与 release handoff | 复制 schema/代码常量、建立第二流程、registry、processor、模型/并发策略或状态机；把环境 workflow 纳入 producer 完成条件 |
| 代码内核 | `task init`、stage-open exact input freeze、stage-close create-once、atomic download/CAS、schema/digest/ref/media hard facts、单对象 `publish-object`、显式 cohort `pool-build` | 来源/选材/创作/review、verdict/issue/approved/cohort/milestone/后继派生、stage-gate registry、semantic wrapper、runner/fleet/claim、自动恢复、execution-state reducer |
| 下游环境 owner | 只读 immutable release handoff，独立执行 import/activate/readback/health/UAT/EAF/promotion/rollback/replay | 改写 producer receipt、cohort、release bytes、producer terminal，或把环境事实冒充 producer 阶段 |

硬约束：

1. 代码同步返回，不等待 AI 回写。
2. verifier 只验证可重复的硬事实，不作语义判断。
3. 每个 approved 对象独立原子 publish；一个对象失败不回滚其它已成功对象。
4. release 必须消费 AI 显式 cohort，禁止隐式 all-publishable。
5. release handoff 必须携带 release ref/digest、完整排序 executionIds 及各自 sequence-009 receipt、cohort ref/digest、milestone、carrier counts、内嵌 content-pool query document/digest 与 producer baseline revision。
6. 每个 execution 的 `release` sequence-009/pass 后还必须 terminal handoff create-once 成功才到 `END`；环境动作是并行下游 workflow，既有 ship CLI 保留但不属于本 Skill。
7. producer receipt 与 immutable handoff facts 是跨会话状态；无 shim、dual-read、legacy fallback 或 sequence-017 兼容。
