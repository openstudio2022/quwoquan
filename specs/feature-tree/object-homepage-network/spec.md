# L1 Domain Service：对象主页网络 (`object-homepage-network`)

> 一句话定位：`object-homepage-network` 是用户主页、圈子/群组主页、共享主页三类对象页的跨域体验与契约收口层。

## 1. 目标与用户价值

`object-homepage-network` 是用户主页、圈子/群组主页、共享主页三类对象页的跨域体验与契约收口层。

## 2. 领域边界

### 本领域拥有

- 拥有跨用户主页、圈子主页与共享主页的对象页呈现合同、交集解释、行动入口和跨页状态交接；底层对象事实仍由来源领域拥有。
- 只能通过本领域公开 command 修改其拥有事实。

### 本领域不拥有

- 不拥有其他 L1 的事实；跨域协作必须使用对方公开 command、query、projection 或 event。
- 不复制 metadata 中的字段、path、错误码和 wire 语义。

### 上下游协作

- 上游：AppRoot Journey 与公开输入事实。
- 下游：直接 L2 能力以及协作 L1 的公开结果。
- 跨域写入：目标领域公开 command；禁止直写目标存储。
- 跨域读取：目标领域公开 query/projection。

## 3. Journey / Scenario 职责

- [`JNY-011 / SCN-026`](../spec.md#scn-026)
  - 本领域负责：在“对象页交集行动深化（同趣围观到破冰升级）”中，组合对象关系与交集解释投影，向对象页交付可理解、可行动的交集结果。
  - 进入条件：用户发起“对象页交集行动深化（同趣围观到破冰升级）”且身份、输入与权限前置成立。
  - 交付给下游的结果：组合对象关系与交集解释投影，向对象页交付可理解、可行动的交集结果，供 `recommendation-platform` 继续处理。
  - 不负责：不写入账号、内容、圈子或会话 owner 事实。

## 4. 业务能力

- [`intersection-unified-experience`](./intersection-unified-experience/spec.md)：以统一的交集事实、置信度、保鲜期和展示契约驱动发现、对象主页、圈子、聊天、个人主页与助理场景

## 5. 领域要求

<a id="req-001"></a>
### REQ-001 三类对象页统一体验验收

- 用户主页、圈子/群组主页、共享主页均使用统一四段式信息架构。
- 任一对象页首屏能在 3 秒内讲清对象身份、与我的关系和可行动作。
- 三类对象页共享视觉组件，但按 user/circle/homepage 保留自然差异。

<a id="req-002"></a>
### REQ-002 对象关系契约与硬债验收

- ObjectRelationEdge、ObjectPageBundle、ObjectPageContext 完成 metadata 与 codegen。
- HomepageType 与 fixture 不再漂移，首发校园和旅游出行对象有明确模板。
- entity-service 主页读模型具备持久化、内容聚合、口碑、相关圈子和关系边。
- 评论可关联 canonicalEntityId 或 homepageId，并能形成 comment_about_entity 关系边。
- canonicalEntityId 与 homepageId 有单一映射合同。

<a id="req-003"></a>
### REQ-003 运营灰度与回滚验收

- 对象页升级可按地域、版本、白名单、experimentBucket、对象类型和环境灰度。
- 生产 App 仍只有一个 prod 包，不出现 app-prod-gray 或 release mock 入口。
- 每个灰度 cohort 可观测曝光、转化、异常率、接口 RT、小艺触发和 dismiss。
- 可按层级关闭小艺主动提示、关系证据可视化、新对象页模板、推荐策略变体。

<a id="req-004"></a>
### REQ-004 埋点到实时推荐闭环验收

- 对象页曝光、交集曝光/点击、关系边点击、Tab 切换、行动、小艺反馈均进入统一行为管道。
- 事件携带 objectType、objectId、canonicalEntityId、tagRefs、entityRefs、relationEdgeIds、intersectionReasonIds、referralSource、feedRequestId、recommendationTraceId、experimentBucket、rolloutCohort。
- 推荐服务能消费对象关系反馈并形成 relation-aware ranking 输入。

<a id="req-005"></a>
### REQ-005 小艺主动服务验收

- 小艺主动提示消费 ObjectPageContext、IntersectionReason、ObjectRelationEdge 和 rollout 策略。
- 主动提示具备置信度、触发原因、冷却时间、可关闭状态。
- impression、click、accept、dismiss 全部回流行为管道。
- 小艺提示不遮挡对象页主操作，不在同一首屏出现多个主动提示。

<a id="req-006"></a>
### REQ-006 三类主页统一采用 身份区 / 交集与小艺区 / 看点区 / 导航区 四段式

- 三类主页统一采用 `身份区 / 交集与小艺区 / 看点区 / 导航区` 四段式。
- 前台文案必须使用用户语言，不向用户暴露 `entity`、`object graph`、`relation edge` 等工程术语。
- 新增 `ObjectPageBundle`，统一返回 `identity / stats / intersectionReasons / highlightItems / contentSections / relatedObjects / assistantContext / rolloutContext`。
- 端侧不得在 UI 拼装关系文案或维护第二套路由、surface、operation、tagRef、entityRef 表。
- 全量功能一次性开发完成，但发布必须可按 `region / city / campus / appVersion / buildNumber / userWhitelist / experimentBucket / objectType / runtimeEnv` 灰度。
- 每个灰度 cohort 必须能独立观测曝光、交集理解、行动转化、异常率、接口 RT、小艺触发率和 dismiss 率。
- 对象页事件统一进入行为管道，至少包括：
- 事件必须携带 `objectType/objectId/canonicalEntityId/tagRefs/entityRefs/relationEdgeIds/intersectionReasonIds/referralSource/feedRequestId/recommendationTraceId/experimentBucket/rolloutCohort`。
- 主动提示必须有置信度、触发原因、冷却时间和可 dismiss 状态。
- 用户接受、点击、忽略、关闭都必须回流行为管道，供推荐和小艺策略学习。

## 6. 领域验收

<a id="dom-001"></a>
### DOM-001 三类对象页统一体验验收

- 条件：本领域收到有效输入且前置领域事实成立。
- 可观察结果：用户主页、圈子/群组主页、共享主页均使用统一四段式信息架构。
- 任一对象页首屏能在 3 秒内讲清对象身份、与我的关系和可行动作。
- 三类对象页共享视觉组件，但按 user/circle/homepage 保留自然差异。
- 禁止结果：前台不暴露 entity、object graph、relation edge 等工程词。；UI 不维护第二套对象关系文案或路由表。

<a id="dom-002"></a>
### DOM-002 对象关系契约与硬债验收

- 条件：本领域收到有效输入且前置领域事实成立。
- 可观察结果：ObjectRelationEdge、ObjectPageBundle、ObjectPageContext 完成 metadata 与 codegen。
- HomepageType 与 fixture 不再漂移，首发校园和旅游出行对象有明确模板。
- entity-service 主页读模型具备持久化、内容聚合、口碑、相关圈子和关系边。
- 评论可关联 canonicalEntityId 或 homepageId，并能形成 comment_about_entity 关系边。
- canonicalEntityId 与 homepageId 有单一映射合同。
- 禁止结果：关系事实只来自 metadata/codegen/后端投影，端侧不得编造。；不恢复旧扁平 tag taxonomy 或旧 resonance 链路。

<a id="dom-003"></a>
### DOM-003 运营灰度与回滚验收

- 条件：本领域收到有效输入且前置领域事实成立。
- 可观察结果：对象页升级可按地域、版本、白名单、experimentBucket、对象类型和环境灰度。
- 生产 App 仍只有一个 prod 包，不出现 app-prod-gray 或 release mock 入口。
- 每个灰度 cohort 可观测曝光、转化、异常率、接口 RT、小艺触发和 dismiss。
- 可按层级关闭小艺主动提示、关系证据可视化、新对象页模板、推荐策略变体。
- 禁止结果：灰度不改变数据真相源。；回滚不得恢复旧对象页并行数据链路。

<a id="dom-004"></a>
### DOM-004 埋点到实时推荐闭环验收

- 条件：本领域收到有效输入且前置领域事实成立。
- 可观察结果：对象页曝光、交集曝光/点击、关系边点击、Tab 切换、行动、小艺反馈均进入统一行为管道。
- 事件携带 objectType、objectId、canonicalEntityId、tagRefs、entityRefs、relationEdgeIds、intersectionReasonIds、referralSource、feedRequestId、recommendationTraceId、experimentBucket、rolloutCohort。
- 推荐服务能消费对象关系反馈并形成 relation-aware ranking 输入。
- 禁止结果：不允许只上报普通点击而丢失对象关系字段。；api_integration 中每个真实行为断言必须在 local_contract mock 行为测试中有对应断言。

<a id="dom-005"></a>
### DOM-005 小艺主动服务验收

- 条件：本领域收到有效输入且前置领域事实成立。
- 可观察结果：小艺主动提示消费 ObjectPageContext、IntersectionReason、ObjectRelationEdge 和 rollout 策略。
- 主动提示具备置信度、触发原因、冷却时间、可关闭状态。
- impression、click、accept、dismiss 全部回流行为管道。
- 小艺提示不遮挡对象页主操作，不在同一首屏出现多个主动提示。
- 禁止结果：小艺不得基于端侧临时拼装上下文生成事实解释。；用户关闭或忽略必须影响后续触发策略。

## 7. 工程归属

- App：`quwoquan_app/lib/ui/intersection`、`quwoquan_app/lib/components/object_page`
- App（协作引用，不用于代码归属）：`quwoquan_app/lib/ui/entity`
- Contracts（协作引用，不用于代码归属）：`quwoquan_service/services/entity-service/contracts`
- Contracts（协作引用，不用于代码归属）：`quwoquan_service/services/content-service/contracts`、`quwoquan_service/services/user-service/contracts`
- Service（协作引用，不用于代码归属）：`quwoquan_service/services/recommendation-service`、`quwoquan_service/services/entity-service`、`quwoquan_service/services/content-service`、`quwoquan_service/services/user-service`
- 测试：
  - `local_contract`：`quwoquan_app/test`
  - `api_integration`：`quwoquan_service/services/entity-service/tests`
  - `user_acceptance`：`quwoquan_ops/tests/acceptance/user_acceptance`

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 三类对象页统一体验验收

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：用户主页、圈子/群组主页、共享主页均使用统一四段式信息架构。
- 完成判定：`DOM-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 运营灰度与回滚验收

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：对象页升级可按地域、版本、白名单、experimentBucket、对象类型和环境灰度。
- 完成判定：`DOM-003` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-003"></a>
### OPEN-003 埋点到实时推荐闭环验收

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：对象页曝光、交集曝光/点击、关系边点击、Tab 切换、行动、小艺反馈均进入统一行为管道。
- 完成判定：`DOM-004` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-004"></a>
### OPEN-004 小艺主动服务验收

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：小艺主动提示消费 ObjectPageContext、IntersectionReason、ObjectRelationEdge 和 rollout 策略。
- 完成判定：`DOM-005` 对应行为满足且真实测试 `spec_ref` 有效
