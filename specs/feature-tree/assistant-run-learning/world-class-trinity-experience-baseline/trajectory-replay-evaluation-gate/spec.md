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
- 每个技能的回放语料必须覆盖恢复（recovery，工具失败后按恢复合同重试成功）、审批（approval，工具提案进入 waiting_approval 中断态）、超时（timeout，工具产生结构化 timeout 失败）与重试（retry，首次失败第二次成功且引用只计一次）四类轨迹，每类至少一条。
- 新增技能而未同步补齐回放覆盖时必须阻断合入。

<a id="req-002"></a>
### REQ-002 回放验证完整公开运行轨迹与真实执行形状

- 回放必须经过与真实运行相同的技能清单、上下文装配、工具准入、规划、证据处理与聚合路径。
- 全部 reactive Case 必须由 production Router 按输入文本路由到期望技能，执行清单使用路由结果而非直接信任请求声明的 SkillID；路由偏离即硬失败。
- proactive Case 必须携带与生产 Trigger→AssistantRun 相同形状的受信 trigger identity（kind、triggerId、occurredAt、subscriptionRef、dedupeKey、deliveryPolicyRef）；缺失、不完整或声明在非 proactive 技能上时执行 fail-closed。proactive-only 技能的全部 Case 必须显式声明 proactive 触发形状。
- 工具选择必须与 Case 期望及技能允许集合一致；缺少关键槽位时必须产生对应反问。
- 用户可见引用只能来自该 Case 的工具结果，最终答案模式必须与聚合终态一致。

<a id="req-003"></a>
### REQ-003 硬失败阻断提示与策略静默回归

- 任一 Case 的技能、工具、澄清槽位、引用或最终答案模式不符合预期时，评测整体失败。
- 覆盖不足、重复 Case 标识或未知技能同样视为硬失败，不得降级为告警或平均分抵消。

<a id="req-004"></a>
### REQ-004 SkillPackageRelease 激活校验评测收据

- 激活输入必须携带评测 receipt：replay corpus assetId、exact package release digest、exact replay corpus asset digest、评测时间与 `passed` 结论（契约实体 `SkillPackageEvaluationReceipt`）。
- receipt 与待激活 release 的 `ReleaseDigest` 或 replay asset 的 assetId/digest 任一不一致、结论非 `passed`、缺评测时间时，激活 fail-closed 并返回 `ASSISTANT.USER.skill_package_evaluation_receipt_invalid`，active 指针不得变化。
- publication artifact 必须内嵌同一 receipt；构建管线只在轨迹回放评测门禁通过后运行，并把评测结论绑定到本次构建的精确 digest。

## 4. 契约引用

- canonical：`quwoquan_service/services/assistant-service/contracts/_shared/assistant_replay_case/schema.yaml`
- skill：`quwoquan_service/services/assistant-service/contracts/_shared/assistant_skill_manifest/schema.yaml`
- event：`quwoquan_service/services/assistant-service/contracts/_shared/assistant_stream_event/schema.yaml`
- aggregation：`quwoquan_service/services/assistant-service/contracts/_shared/aggregation_state/schema.yaml`
- activation receipt：`quwoquan_service/services/assistant-service/contracts/assistant/skill_package_release/fields.yaml`（`ActivateSkillPackageCommand.evaluationReceipt` / `SkillPackageEvaluationReceipt`）与同目录 `errors.yaml`（`ASSISTANT.USER.skill_package_evaluation_receipt_invalid`）

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 技能目录与回放覆盖保持同步

- GIVEN 技能目录含当前全部可装配技能
- WHEN 评测加载技能目录与回放 Case
- THEN 每个技能至少对应十条不同输入且 Case 标识全局唯一
- THEN 每个技能语料覆盖 recovery、approval、timeout、retry 四类轨迹，缺任一类即整体失败
- THEN 未知技能、缺少期望结果或覆盖不足时整体失败

<a id="gwt-002"></a>
### GWT-002 轨迹偏离时阻断合入

- GIVEN 回放 Case 声明预期工具、澄清槽位、引用和最终答案模式
- WHEN Case 经过统一 Agent 主线执行
- THEN 全部 reactive Case 的输入由 production Router 命中期望技能，proactive Case 携带完整受信 trigger identity，任一偏离即整体失败
- THEN 实际选中技能和工具与预期一致，工具不越过技能允许集合
- THEN 澄清槽位与聚合终态一致，用户可见引用仅来自该次工具结果
- THEN 恢复/重试轨迹恰好产生一条聚合完成事件且重试成功的引用只计一次
- THEN 审批轨迹进入 waiting_approval 中断态且不产生聚合完成事件
- THEN 超时轨迹产生结构化 timeout 失败并阻断最终回答
- THEN 任一硬断言偏离时仓库合入门禁失败

<a id="gwt-003"></a>
### GWT-003 激活被评测收据门禁保护

- GIVEN 一个已 Stage 的 SkillPackageRelease 与其 replay corpus asset
- WHEN 激活输入携带的评测 receipt 与该 release 的 package digest、replay asset 的 assetId/digest 完全一致且结论为 `passed`
- THEN 激活成功切换 active 指针
- THEN receipt 缺失、任一 digest 或 assetId 不符、结论非 `passed` 或缺评测时间时，激活返回 `ASSISTANT.USER.skill_package_evaluation_receipt_invalid` 且 active 指针不变

## 6. 依赖

- 前置要求：[`world-class-trinity-experience-baseline`](../spec.md) 的范围、要求与 SIT。
- 上游事实：技能清单、冻结策略、上下文槽位、工具结果和模型结构化决策。
- 下游结果：提示、策略和技能目录变更的可重复质量准入结论。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

（无）
