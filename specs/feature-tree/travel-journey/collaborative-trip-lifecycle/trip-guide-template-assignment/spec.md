# L3 Story：领队导游模板与任务归属 (`trip-guide-template-assignment`)

> 所属能力：[共同旅行全生命周期](../spec.md)
>
> Journey / Scenario：[`JNY-013 / SCN-030`](../../../spec.md#scn-030)、[`SCN-031`](../../../spec.md#scn-031)
>
> 设计归属：[`L2 DEC-001`](../design.md#dec-001)

## 1. 用户价值

作为领队、持证导游或本地专家，我希望复用经过验证的行程模板、明确分工并保留专业署名，从而减少重复协调，同时让 AI 承担行政提醒和通用事实而不取代我的专业服务身份。

## 2. 范围与非目标

### In Scope

- TripPlanTemplate 创建/复制/修订、GuideAssignment、任务状态、讲解/来源署名和公开资质引用。

### Out of Scope

- 导游资格审核真相、私人导游撮合、收费交易、劳动关系或旅行社业务审批。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 模板、任务与专业身份保持独立可追溯

- Template 只包含可复用计划结构、建议与来源引用，不包含历史成员、私人住宿、聊天或 Connector 数据。
- `CreateTripPlanFromTemplate` 必须由模板 owner 发起，并在新 Trip 的首次事务中冻结模板版本、公开 Post 与专业 Persona 署名；住宿只生成待确认占位，不复制原住宿事实。
- GuideAssignment 必须引用 Trip、任务、负责人 Persona、声明角色和状态；资质展示只引用 User 领域公开声明，Travel 不复制或认证资质。
- AI 生成的通用讲解必须标明来源；专业讲解和路线经验保留作者署名，助手不得冒充持证导游或公共应急服务。

## 4. 契约引用

- object / projection：`travel.TripPlanTemplate`、`travel.TripPlan`、`travel.TripGuideAssignment`
- operation：`travel.trip_plan_template.CreateTripPlanTemplate`、`travel.trip_plan.CreateTripPlanFromTemplate`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 领队复用模板且不带入旧行程隐私

- GIVEN 领队拥有一份含公开路线与专业讲解的模板，原 Trip 含成员、住宿和聊天引用。
- WHEN 领队基于模板创建新 Trip 并给助理导游分配集合任务。
- THEN 新 Trip 只复制允许的结构、公开来源和署名，旧成员、住宿、Moment、聊天与 Connector 数据均不存在。
- AND 任务状态与负责人可独立变更，专业讲解署名不被助手覆盖。

## 6. 依赖

- 前置要求：Persona/公开资质 Reader、TripPlan command 与内容来源可用。
- 上游事实：模板、角色声明、任务与公开讲解引用。
- 下游结果：新 Trip、GuideAssignment、Assistant 讲解上下文与任务提醒。
- 父级设计：`DEC-001`

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 模板复用与导游角色旅程尚未形成商用证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：仍缺 Assistant 提醒、法律运营文案审核、真实 API integration、三环境及双端物理真机证据，因此不能宣称该角色旅程已可商用。
- 当前本地事实：组织者可创建隐私剥离后的独立模板、以 CAS version 和同一重试幂等键修改模板名称/适用说明且保留原计划项与署名，并可从 active 成员中按公开昵称创建或改派任务。任务命令同样保留 CAS version 与同一重试幂等键，持证导游的公开资质引用始终绑定当前负责人。
- 当前展示事实：App 可显示负责人公开昵称、角色与任务，并允许负责人或组织者接受、开始和完成。模板复制使用 typed command、冻结署名以及公开 Persona/Post fail-closed Reader。
- 证据边界：上述实现目前只有定向 local contract 与 analyze 证据，不能代替 API、环境和物理真机验收。
- 完成判定：`GWT-001` 具有 Travel/User local_contract、api_integration 和角色 user_acceptance 直接 `spec_ref`；法律与运营文案审核通过。
- 依赖：User Persona/资质公开 Reader、Assistant trigger 与 Travel App guide surface。
