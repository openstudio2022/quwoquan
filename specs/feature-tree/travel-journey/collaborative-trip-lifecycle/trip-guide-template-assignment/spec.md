# L3 Story：旅行模板来源、任务与专业署名 (`trip-guide-template-assignment`)

> 所属能力：[共同旅行全生命周期](../spec.md)
>
> Journey / Scenario：[`JNY-013 / SCN-030`](../../../spec.md#scn-030)、[`SCN-031`](../../../spec.md#scn-031)
>
> 设计归属：[`L2 DEC-001`](../design.md#dec-001)

## 1. 用户价值

作为领队、持证导游或本地专家，我希望复用经过验证的行程模板、明确分工并保留专业署名，从而减少重复协调，同时让 AI 承担行政提醒和通用事实而不取代我的专业服务身份。

## 2. 范围与非目标

### In Scope

- 把公开路线/讲解/内容作为 source reference 转换为待确认的 GatheringPlan proposal。
- GatheringPlan task item 的 assignee Persona reference、任务状态、讲解来源与专业署名。
- User owner 的公开专业声明只读引用，以及 Assistant 通用讲解的来源边界。
- legacy TripPlanTemplate/TripGuideAssignment 到 proposal source/task item/Persona reference 的历史 crosswalk。

### Out of Scope

- 导游资格审核真相、私人导游撮合、收费交易、劳动关系或旅行社业务审批。
- 独立 Template/GuideAssignment aggregate、Travel App guide surface、复制旧成员/住宿/聊天/Connector 数据或由 Assistant 冒充专业身份。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 来源、任务与专业身份保持独立可追溯

- 可复用来源只包含公开计划结构、建议、source version 与署名引用，不包含历史成员、私人住宿、聊天、个人记忆或 Connector 数据。
- 应用来源只能形成绑定目标 Gathering/current Plan revision 的 typed proposal；Host 确认后由 GatheringPlan owner commit 新 Revision，住宿只生成待确认 item，不复制原事实。
- 专业分工使用 GatheringPlan task item 的 assignee Persona reference、声明角色与状态；资格展示只读取 User owner 公开声明，本领域不复制或认证资质。
- AI 生成的通用讲解必须标明来源；专业讲解和路线经验保留作者署名，助手不得冒充持证导游或公共应急服务。
- legacy Template/GuideAssignment ID 只存在于迁移 receipt，不得恢复 create/copy/assign operation。

## 4. 契约引用

- current target：Circle `GatheringPlan` proposal/Revision/task item，User `Persona` 公开声明，Content/Assistant source reference。
- canonical：`quwoquan_service/services/circle-service/contracts/circle_management/gathering_plan/operations.yaml`
- historical crosswalk：`TripPlanTemplate -> typed proposal source refs`，`TripGuideAssignment -> Plan task item assignee Persona ref + public professional claim`。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 领队复用公开来源且不带入旧旅行隐私

- GIVEN 领队选择一组含公开路线与专业讲解的来源，来源旅行曾包含成员、私人住宿、Experience、聊天与 Connector 数据。
- WHEN 领队把来源转换为目标 GatheringPlan proposal，Host 确认后为助理导游建立集合 task item。
- THEN 新 Revision 只包含允许的 typed items、公开来源和署名，旧参与者、私人住宿、Experience、聊天与 Connector 数据均不存在。
- AND task 状态与 assignee 通过 Plan Revision 可追溯变更，公开专业声明由 User owner 读取，专业讲解署名不被助手覆盖。

## 6. 依赖

- 前置要求：Persona/公开声明 Reader、GatheringPlan proposal/commit 与 Content/Assistant 来源可用。
- 上游事实：公开来源、角色声明、task item 与讲解引用。
- 下游结果：新 Plan Revision、task assignee、Assistant 讲解上下文与任务提醒。
- 父级设计：`DEC-001`、`DEC-002`

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 模板来源、任务与专业署名尚未形成商用证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：当前没有可声明已落地的 Travel Template/GuideAssignment runtime 或页面；尚缺 source-to-proposal production Remote、task item/Persona 公开声明组合、Assistant 提醒与外部证据 Provider、法律运营文案审核、跨域 API integration 及 Android/iPhone 证据。
- 完成判定：`GWT-001` 由 Circle/User/Content/Assistant local_contract、真实跨域 api_integration 和 Android/iPhone 角色 user_acceptance 直接覆盖；Provider unavailable 结构化降级，隐私字段复制与署名覆盖均为零，法律与运营文案审核通过。
- 依赖：GatheringPlan proposal/task item、User Persona/公开声明 Reader、Content/Assistant source Reader、Integration Provider 与 Chat Board/App production Remote。
