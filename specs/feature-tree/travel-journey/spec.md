# L1 Domain Service：共同旅行旅程 (`travel-journey`)

> 一句话定位：以可共同维护、可追溯修订、可连接内容与关系的 Trip 事实，让一次出行从计划持续生长为共同时间线。

## 1. 目标与用户价值

为 2–8 人、3–7 天国内自由行的组织者和参与者提供“活的共同旅行时间线”：一次维护吃玩住行，群内同步变化，行中获得下一步与讲解，随拍自然归档，行后形成可编辑、可分享的游记。领队、导游和本地专家可以复用模板与署名内容，创作者内容可以被真实行程采用，搭子关系可从共同经历继续沉淀。

## 2. 领域边界

### 本领域拥有

- `TripPlan`、不可变 `TripPlanRevision`、`TripPlanItem`、`TripMembership`、`TripMoment`、`TripPlanPlacement`、`TripShareSnapshot`、`TripPlanTemplate` 与 `TripGuideAssignment` 的生命周期和写入决定权。
- 从上述事实派生的 `TripTimelineView` 与 `TripMapView`，以及 Trip/Item 与外部业务对象之间的 typed link。

### 本领域不拥有

- Conversation、Message 与成员名册；owner：[`chat-conversation`](../chat-conversation/spec.md)。
- Circle、Gathering 与参与者；owner：[`circle-community`](../circle-community/spec.md)。
- Post、LocalPostDraft、MediaAsset；owner：[`discovery-content`](../discovery-content/spec.md)。
- Persona、Follow 与公开资质声明；owner：[`user-identity-profile-relationship`](../user-identity-profile-relationship/spec.md)。
- Skill、AssistantRun、Trigger、Evidence 与 Presentation；owner：[`assistant-run-learning`](../assistant-run-learning/spec.md)。

### 上下游协作

- 上游：Conversation/Circle/Gathering 放置上下文、Persona 权限、Post/MediaAsset 引用、Entity/Place 事实及用户确认的助手提案。
- 下游：当前 Trip Revision、时间线、地图、变化事件、分享快照和游记草稿请求。
- 跨域写入：只调用目标领域公开 command；本领域不直写 Chat、Circle、Content、User 或 Assistant 存储。
- 跨域读取：使用所属领域公开 query/projection，并保存 typed reference 与来源版本。
- 异步协作：发布 Trip revision、placement、moment、lifecycle 与 share snapshot 事件供 Assistant、Chat、Circle、Content 和观测消费者使用。

## 3. Journey / Scenario 职责

- [`JNY-013 / SCN-030`](../spec.md#scn-030)
  - 本领域负责：把经确认的计划提案写成 Trip、Revision、Item、Membership 与 Placement 事实。
  - 进入条件：组织者身份、目标共享场景和计划输入有效。
  - 交付给下游的结果：可共同查看和继续修订的当前 TripPlan。
  - 不负责：不把 Assistant 文本或 Chat Message 当 Trip 真相源。
- [`JNY-013 / SCN-031`](../spec.md#scn-031)
  - 本领域负责：以不可变 Revision 原子推进当前计划，计算可读 diff、严重等级与受影响成员，并发布变化事实。
  - 进入条件：操作者拥有组织权限，expected revision 与当前事实一致。
  - 交付给下游的结果：新的 current Revision 和可供主动提醒的 typed event。
  - 不负责：不决定通知频控、静默与投递渠道。
- [`JNY-013 / SCN-032`](../spec.md#scn-032)
  - 本领域负责：经用户确认把 Moment 或 Post link 关联到 Day/Item，并从同一事实投影时间线和地图。
  - 进入条件：Trip、目标 Item 与引用对象可见且未失效。
  - 交付给下游的结果：顺序稳定、可追溯且可删除的 Moment/link 与投影。
  - 不负责：不复制媒体字节、Post 正文或连续位置轨迹。
- [`JNY-013 / SCN-033`](../spec.md#scn-033)
  - 本领域负责：冻结隐私裁剪后的分享范围和 TripShareSnapshot，并向 Content 请求 LocalPostDraft。
  - 进入条件：调用方可分享目标 Trip 范围，且敏感字段裁剪通过。
  - 交付给下游的结果：整段、单日、单点、路线或 Moment 集合快照及草稿来源引用。
  - 不负责：不自动发布内容，不创建或修改关系。

## 4. 业务能力

- [`collaborative-trip-lifecycle`](./collaborative-trip-lifecycle/spec.md)：组合 Trip 计划、修订、成员与共享放置、Moment/内容关系、时间线/地图、分享、模板和导游任务的完整生命周期。

## 5. 领域要求

<a id="req-001"></a>
### REQ-001 Trip 当前事实与历史修订单轨

- `TripPlan` 只引用一个 current Revision；每次结构或计划项变更必须生成新的不可变 Revision，并以 CAS 原子推进。
- 失败、冲突或未确认提案不得改变 current Revision，也不得以 Chat Message、Assistant Artifact 或 App cache 作为当前计划。

<a id="req-002"></a>
### REQ-002 多共享场景、多行程与隐私边界

- 一个 Trip 可放置于多个 Conversation/Circle，一个共享场景可放置多个 Trip/Gathering；目标不明确时调用方必须消歧。
- 时间线与地图不得记录连续实时轨迹；公开 ShareSnapshot 必须移除私人住宿细节、联系方式、成员名单和实时精确位置。

## 6. 领域验收

<a id="dom-001"></a>
### DOM-001 共同旅行事实所有权与收敛

- 条件：多个成员在同一共享场景创建、修订、记录和分享 Trip。
- 可观察结果：当前 Revision 唯一且历史不可变，Moment/Post 只以引用关联，时间线与地图收敛到同一事实，跨域写入均有公开 command receipt。
- 禁止结果：不得双写 Trip、复制 Post/MediaAsset、手工写投影、以消息或助手状态代替 Trip、泄露公开分享禁止字段。

## 7. 工程归属

- App：`quwoquan_app/lib/ui/travel`
- Contracts：`quwoquan_service/services/travel-service/contracts`
- Service：`quwoquan_service/services/travel-service`
- Ops：`quwoquan_service/services/travel-service/environments`
- 测试：
  - `local_contract`：`quwoquan_service/services/travel-service/tests/local_contract`
  - `api_integration`：`quwoquan_service/services/travel-service/tests/api_integration`

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 共同旅行领域端到端与真环境准出未完成

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：缺 AppRoot 共同旅行端到端 UAT、完整跨域 Reader/command/event、真实存储执行、受管环境激活回读与物理真机证据；App 已有 Trip 目录、创建、修订、时间线、地图、Moment inbox、模板、导游任务和分享页面及 typed Remote local contract，不能据此替代跨域与环境验收。
- 完成判定：`DOM-001` 具有对象 local_contract、跨对象 api_integration 和 AppRoot 共同旅行 user_acceptance 直接 `spec_ref`；同一候选通过 Alpha/Beta/Gamma 与 Android/iPhone 物理真机，Prod 另行完成灰度和回滚。
- 依赖：Assistant active Skill package、Chat/Circle Placement、Content draft/media、User Persona 与 Runtime Provider/Connector 能力。
