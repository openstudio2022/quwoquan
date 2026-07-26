# L1 Domain Service：全局搜索体验 (`global-search-experience`)

> 一句话定位：为用户提供统一的跨领域搜索入口、两阶段结果合同、反馈闭环和可验证发布门。

## 1. 目标与用户价值

统一搜索覆盖联系人、会话、内容、圈子、主页、地点和网络结果，在本地联想与云侧最终结果之间保持清晰合同，并将反馈归因到搜索和推荐。

## 2. 领域边界

### 本领域拥有

- 拥有 canonical 搜索请求、对象分类、搜索派生读模型、最近搜索、结果编排和搜索反馈的生命周期与写入决定权。
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

- [`JNY-007 / SCN-012`](../spec.md#scn-012)
  - 本领域负责：在“1v1 私信与打招呼升级”中检索联系人、用户与可进入主页，并将 canonical 对象标识和入口意图交付给会话领域。
  - 进入条件：用户从统一搜索入口发起联系人、用户或主页查询。
  - 交付给下游的结果：可导航的搜索结果与明确的私信或打招呼入口意图，供 `chat-conversation` 继续处理。
  - 不负责：不创建会话、不改变关系状态，也不复制聊天或用户领域的权威事实。
- [`JNY-005 / SCN-011`](../spec.md#scn-011)
  - 本领域负责：在“全局搜索查询与筛选”中，组合各领域公开搜索投影，执行查询、筛选和反馈归因，并返回可导航的搜索结果。
  - 进入条件：用户发起“全局搜索查询与筛选”且身份、输入与权限前置成立。
  - 交付给下游的结果：组合各领域公开搜索投影，执行查询、筛选和反馈归因，并返回可导航的搜索结果，供 `discovery-content` 继续处理。
  - 不负责：不修改被搜索对象，也不在搜索域复制其写模型。
- [`JNY-009 / SCN-017`](../spec.md#scn-017)
  - 本领域负责：在“内容与页面上下文感知问答”中，组合各领域公开搜索投影，执行查询、筛选和反馈归因，并返回可导航的搜索结果。
  - 进入条件：`user-identity-profile-relationship` 已交付其公开结果。
  - 交付给下游的结果：组合各领域公开搜索投影，执行查询、筛选和反馈归因，并返回可导航的搜索结果，形成该场景中本领域负责的终态。
  - 不负责：不修改被搜索对象，也不在搜索域复制其写模型。
- [`JNY-009 / SCN-019`](../spec.md#scn-019)
  - 本领域负责：在“搜索 handoff 与统一 grounding”中，组合各领域公开搜索投影，执行查询、筛选和反馈归因，并返回可导航的搜索结果。
  - 进入条件：`assistant-run-learning` 已交付其公开结果。
  - 交付给下游的结果：组合各领域公开搜索投影，执行查询、筛选和反馈归因，并返回可导航的搜索结果，供 `discovery-content` 继续处理。
  - 不负责：不修改被搜索对象，也不在搜索域复制其写模型。

## 4. 业务能力

- [`cross-domain-search`](./cross-domain-search/spec.md)：提供从一级页面进入两段式全屏搜索，并完成最近记录、实时联想、独立网络结果、语音转词与 `小趣搜` 结果查看的完整链路。
- [`search-provider-routing-and-storage-topology`](./search-provider-routing-and-storage-topology/spec.md)：统一搜索 contract、对象 taxonomy、Provider 路由、显式降级、本地搜索生命周期与云侧派生读模型，为全屏搜索和页面内 picker 提供同一查询边界。

## 5. 领域要求

<a id="req-001"></a>
### REQ-001 global search experience 领域边界与商用主链路落地验收

- 领域边界、上下游依赖、工程映射和服务治理清晰；search-service（domain=search，18095）为云侧 canonical 入口。
- `content.post`、`entity.homepage`、`circle.circle`、`circle.group`、`user.profile` 与第一方 `location.place` 必须投影到统一索引 `quwoquan_objects`。
- App 的 `RemoteSearchRepository` 必须通过 `CloudHttpClient` 与生成的 path 调用 `/search`，并透传 canonical 商用字段。
- `location.place` 的直达路由、冷启动与进程恢复必须经 canonical `/search` 的受控 `ids` 精确匹配重新读取；App 只消费 `SearchLocationPlaceHitView`，不得用 route extra 或裸 Map 伪造详情。
- 精确读取返回 `entity.homepage` 时，地点落地页必须跳转该主页；无命中时显示结构化不可用恢复态并回到搜索，不得保留泛化标题或过期地址。
- 搜索反馈、热力与排序信号必须回流推荐 Feed，结果排序必须能解释 `termHeat` 的贡献。
- gamma 环境的网关必须使 `/search` 成功返回查询结果，并使 `/search/feedback` 接受反馈；执行证据只保存在测试与运行产物中。
- 两阶段商用合同成立：suggest 本地对象即时，result 云侧最终结果不混入本地对象。
- 搜索准确性、可重复性和热力推荐闭环必须具备 `local_contract`、`api_integration` 与 `user_acceptance` 证据；真集群实测容量和版本落盘由对应 Story 的阻断级 `OPEN` 管理。

<a id="req-002"></a>
### REQ-002 `integration.location_poi`：澄清为**创作 / 附近场景的外部 gateway 数据源**（POI picker、发布定位、附近搜索），**不作为统一 result 对象**进入 canonical `/search` 召回

- `integration.location_poi`：澄清为**创作 / 附近场景的外部 gateway 数据源**（POI picker、发布定位、附近搜索），**不作为统一 result 对象**进入 canonical `/search` 召回；第一方地点 result 对象由 `location.place` 承载（同一地点只出现一次，单一真相源）。
- 需要在不增加额外学习成本的前提下统一维护搜索路由、埋点、请求上下文和结果编排的平台与前端团队。
- 联系人/聊天记录直达会话、网络结果进入独立结果页的统一跳转语义。
- canonical `search(request)` 接口、`mode=suggest|result`、`objectTypes` 与统一搜索结果模型。
- 面向 AI 的 web-search-like query-first 检索语义，以及 `web.document + quwoquan objects` 的统一召回接口。
- 输入过程中只定位已有对象；未连接圈子、未关注地点、未连接的人，以及图片/视频/长文正式结果不得出现。
- `交集` Tab 展示交集概览、交集推荐区和交集发现流，每张卡必须展示交集原因。
- 统一 object taxonomy：`web.document`、`chat.contact`、`chat.conversation`、`chat.message`、`circle.group`、`circle.circle`、`content.post`、`entity.homepage`、`user.profile`、`location.place`。`result` 阶段云侧最终结果只含 `content.post / entity.homepage / location.place / 相关搜索词 / 小趣`；`integration.location_poi` 仅作创作或附近场景的外部 gateway 数据源，不作为统一 result 对象。
- 统一 search contract 生成 App / cloud client / AI agent tool 共用 schema，避免端云与 agent 维护第二套搜索接口。
- 统一搜索 contract 采用 query-first 的 web-search-like 形态，优先让 AI 生成关键词串和少量简单条件，而不是复杂嵌套 DSL。

## 6. 领域验收

<a id="dom-001"></a>
### DOM-001 global search experience 领域边界与商用主链路落地验收

- 条件：本领域收到有效输入且前置领域事实成立。
- 可观察结果：领域边界、上下游依赖、工程映射和服务治理清晰
- search-service（domain=search，18095）为云侧 canonical 入口。
- `content.post`、`entity.homepage`、`circle.circle`、`circle.group`、`user.profile` 与第一方 `location.place` 可从统一索引 `quwoquan_objects` 检索。
- App 通过 `RemoteSearchRepository`、`CloudHttpClient` 与生成的 path 完成 `/search` 请求并保留 canonical 字段。
- `location.place` 可由其 canonical `placeId` 精确重新读取；已提升到 `entity.homepage` 的结果跳转主页，不存在的结果进入可恢复不可用态。
- 搜索反馈、热力与排序信号进入推荐 Feed。
- 结果页排序 term-heat 已闭环。
- gamma 环境经网关调用 `/search` 返回 200、调用 `/search/feedback` 返回 202。
- 两阶段商用合同成立：suggest 本地对象即时，result 云侧最终结果不混入本地对象。
- 搜索准确性、可重复性和热力推荐闭环具备 `local_contract`、`api_integration` 与 `user_acceptance` 证据。
- 真集群 measured 容量和版本落盘仍作为发布阻断项跟踪。
- 禁止结果：chat.* 私有对象 local_only，绝不上云做跨用户召回。
- location.place 与 entity.homepage 互斥单源，同一地点只出现一次。
- integration.location_poi 不作为统一 result 对象。

## 7. 工程归属

- App：`quwoquan_app/lib/ui/search`、`quwoquan_app/lib/core/providers/app_providers.dart`
- Contracts：`quwoquan_service/services/search-service/contracts`
- Contracts（协作引用，不用于代码归属）：`quwoquan_service/services/user-service/contracts`、`quwoquan_service/services/content-service/contracts`
- Service：`quwoquan_service/services/search-service`
- Service（协作引用，不用于代码归属）：`quwoquan_service/services/user-service`、`quwoquan_service/services/entity-service`、`quwoquan_service/services/content-service`、`quwoquan_service/services/chat-service`、`quwoquan_service/services/circle-service`
- 测试：
  - `local_contract`：`quwoquan_ops/tests/local_contract`
  - `api_integration`：`quwoquan_ops/tests/acceptance/api_integration`
  - `user_acceptance`：`quwoquan_ops/tests/acceptance/user_acceptance`

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 global search experience 商用运行证据准出

- 类型：`external_blocker`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：领域边界、canonical search-service、分层测试与直接 `spec_ref`
  已落地；Gamma-local 已使用统一材料器提供日志 Port 替身，不要求真实 SLS 租户或
  凭据，当前仍缺 production Remote 真机 Journey CaseResult 与同源黄金指标样本。
- 目标：关闭直属能力中所有发布阻断，并证明搜索结果、最近搜索、标签过滤、
  搜索反馈和 SLS 漏斗来自同一 commercial contract。
- 完成判定：`DOM-001` 的 Gamma-local 真机 CaseResult、requestId/traceId 与 SLO 证据完整，
  且直属节点无未关闭的发布阻断。
