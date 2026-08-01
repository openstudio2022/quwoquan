# L3 Story：Agent 轨迹回放评测门禁 (`trajectory-replay-evaluation-gate`)

> 所属能力：[`world-class-trinity-experience-baseline`](../spec.md)
>
> Journey / Scenario：[`JNY-009 / SCN-017`](../../../spec.md#scn-017)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为依赖小趣完成任务的用户，我希望提示词、策略和技能升级不会悄悄破坏原本正确的工具选择、信息澄清、引用边界或回答完整度。

## 2. 范围与非目标

### In Scope

- 覆盖全部已注册技能的版本化轨迹回放语料
- 对工具选择、槽位澄清、引用来源和最终答案模式的确定性验收
- 在提示、策略和技能目录变更进入主线前阻断轨迹回归

### Out of Scope

- 以回放结果替代真实模型 Provider、真实工具或端云用户验收
- 用单一总分掩盖安全、引用或回答边界硬失败
- 在生产运行路径装配测试模型或测试工具

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 每个已注册技能具有足量且可追踪的回放覆盖

- 技能目录中的每个技能必须至少具有十条不同用户输入的回放 Case。
- 每条 Case 必须具有稳定标识，并绑定预期技能、领域和最终答案模式。
- 新增技能而未同步补齐回放覆盖时必须阻断合入。

<a id="req-002"></a>
### REQ-002 回放验证完整公开运行轨迹

- 回放必须经过与真实运行相同的技能清单、上下文装配、工具准入、规划、证据处理与聚合路径。
- 工具选择必须与 Case 期望及技能允许集合一致；缺少关键槽位时必须产生对应反问。
- 用户可见引用只能来自该 Case 的工具结果，最终答案模式必须与聚合终态一致。

<a id="req-003"></a>
### REQ-003 硬失败阻断提示与策略静默回归

- 任一 Case 的技能、工具、澄清槽位、引用或最终答案模式不符合预期时，评测整体失败。
- 覆盖不足、重复 Case 标识或未知技能同样视为硬失败，不得降级为告警或平均分抵消。

## 4. 契约引用

- canonical：`quwoquan_service/services/assistant-service/contracts/_shared/assistant_replay_case/schema.yaml`
- skill：`quwoquan_service/services/assistant-service/contracts/_shared/assistant_skill_manifest/schema.yaml`
- event：`quwoquan_service/services/assistant-service/contracts/_shared/assistant_stream_event/schema.yaml`
- aggregation：`quwoquan_service/services/assistant-service/contracts/_shared/aggregation_state/schema.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 技能目录与回放覆盖保持同步

- GIVEN 技能目录含当前全部可装配技能
- WHEN 评测加载技能目录与回放 Case
- THEN 每个技能至少对应十条不同输入且 Case 标识全局唯一
- THEN 未知技能、缺少期望结果或覆盖不足时整体失败

<a id="gwt-002"></a>
### GWT-002 轨迹偏离时阻断合入

- GIVEN 回放 Case 声明预期工具、澄清槽位、引用和最终答案模式
- WHEN Case 经过统一 Agent 主线执行
- THEN 实际选中技能和工具与预期一致，工具不越过技能允许集合
- THEN 澄清槽位与聚合终态一致，用户可见引用仅来自该次工具结果
- THEN 任一硬断言偏离时仓库合入门禁失败

## 6. 依赖

- 前置要求：[`world-class-trinity-experience-baseline`](../spec.md) 的范围、要求与 SIT。
- 上游事实：技能清单、冻结策略、上下文槽位、工具结果和模型结构化决策。
- 下游结果：提示、策略和技能目录变更的可重复质量准入结论。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 全量真实路由与 package 激活评测收据尚未闭环

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺全部 reactive Case 经 production routing、proactive Case 经受信 trigger identity，以及 SkillPackageRelease 激活对 package/corpus exact digest 评测收据的校验；当前 Runner 执行只读取独立 request 与 production manifest 工具策略，poison expectation 不改变 transcript，每个 Skill manifest 已显式绑定版本化 replay asset 且 asset digest 已进入 Skill release digest。
- 完成判定：全部 reactive Case 经 production routing、proactive Case 经受信 trigger identity，且 release 激活校验 exact package/corpus digest 的评测 receipt；补齐恢复、审批、超时与重试轨迹。
