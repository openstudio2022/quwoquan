# L2 Business Capability：跨领域搜索 (`cross-domain-search`)

> 所属领域：[`global-search-experience`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

提供从一级页面进入两段式全屏搜索，并完成最近记录、实时联想、独立网络结果、语音转词与 `小趣搜` 结果查看的完整链路。

## 2. 范围与非目标

### In Scope

- suggest 阶段本地快速检索（chat/contact/circleGroup 本地命名空间）。
- result 阶段云侧最终结果（content.post/user.profile/entity.homepage/location.place/相关词/小趣）与固定 Tab。
- 最近搜索本地+云同步与记录管理态。
- 降级横幅、空态/错误态、权限态与单域降级不阻塞整页。
- 搜索默认页/结果页曝光、停留、referralSource、feedRequestId 埋点归因链。

### Out of Scope

- 各域底层召回与排序实现。
- 交集 Tab 端侧单源收口（归 search-intersection-consumption / 并发 intersection 会话）。

## 3. Journey / Scenario 贡献

- [`JNY-005 / SCN-011`](../../spec.md#scn-011)
  - 本能力接收：该 Scenario 进入本能力边界的已授权主体与 canonical 输入。
  - 本能力处理：提供从一级页面进入两段式全屏搜索，并完成最近记录、实时联想、独立网络结果、语音转词与 `小趣搜` 结果查看的完整链路。
  - 本能力输出：直属 Story 组合产生的可观察结果与明确失败终态。
  - 失败时终态：保留已确认事实，并返回可恢复的 canonical failure。

## 4. Story



- [`circle-facet-search-and-filter`](./circle-facet-search-and-filter/spec.md)：搜索聚合分区使用“讨论”、消息 group 使用“群聊”、Circle 对象使用“圈子”。
- [`full-screen-search-shell-and-entry`](./full-screen-search-shell-and-entry/spec.md)：用户无需输入即可看到继续搜索和产生兴趣的真实启发内容。
- [`local-chat-search-contract`](./local-chat-search-contract/spec.md)：页面与业务层只允许调用 canonical `search(request)`，不得直接依赖聊天域搜索方法名。
- [`multi-domain-result-composition`](./multi-domain-result-composition/spec.md)：输入“钱”可预览并打开发布态“东钱湖”实体主页。
- [`recent-search-sync-and-voice-asr`](./recent-search-sync-and-voice-asr/spec.md)：local_contract 与真实 Mongo api_integration 覆盖相同去重、receipt、owner isolation 行为。
- [`search-intersection-consumption`](./search-intersection-consumption/spec.md)：connected / discovery / intersection_lead 三组互斥，connected 区不展示交集句。
- [`xiaoqu-entry-handoff`](./xiaoqu-entry-handoff/spec.md)：SearchXiaoquResults 不再返回固定 spec/knowledge 占位 citation。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 两阶段跨域搜索旅程 SIT（suggest 本地 + result 云侧）

- suggest 阶段本地快速检索按 联系人/聊天记录/已加入圈子/已关注地点/已关注的人/推荐搜索词 组织，无命中分组隐藏；本地对象不进 result。
- result 阶段固定 Tab 小趣/全部/交集/图片/视频/长文，最终结果只来自云侧；全部 Tab 承载用户分区、实体顶卡与内容流。
- Tag 明确作为 filters.tags 过滤维度，不作为独立结果对象或结果 section；动态筛选首批设计只开放 location/circle 云侧 facet。
- 最近搜索记录 query+launch_context+category_context+timestamp，本地+云同步，支持管理态删除/清空。
- 远端降级/能力受限时由 degradeSignals 驱动降级横幅；单域失败只显该域降级，不阻塞整页。
- 搜索默认页/结果页曝光、停留、referralSource、feedRequestId 归因链可观测。
- 搜索专有事件按 requestId 形成提交/非空或零结果/点击/筛选/非空结果停留漏斗，原始 query、objectId、userId 不进入产品遥测。
- 三项黄金指标在 SLS 聚合、大盘和至少 100 样本告警中同源：有效搜索成功率 ≥35%、首个可操作结果 P95 ≤1.5s、结果到有效行动率 ≥20%。

<a id="req-002"></a>
### REQ-002 命名空间限定在本地：`chat.contact / chat.conversation / chat.message`（`local_only`）与 `circle.group` 本地全量

- 命名空间限定在本地：`chat.contact / chat.conversation / chat.message`（`local_only`）与 `circle.group` 本地全量；未连接圈子、未关注地点、未连接的人，以及图片/视频/长文正式结果不得出现。
- 输入后本地分段必须即时替换默认态，并保持搜索框、取消和结果区域的稳定视觉反馈。
- 键盘保持焦点
- 点击“搜索网络结果”前不得因云侧慢请求卡住输入、删除或返回。
- App 可保留本地 query/session 上下文用于最近搜索、归因和 AB 粘性，但不得把 suggest 本地 hit 作为 result 数据源。
- 结果页可以保留上一页路由栈，但结果数据与可访问性查找必须限定在 `SearchNetworkResultsPage`；offstage suggest 不得被当作结果页内容。
- 搜索默认页与结果页必须记录曝光、停留、`referralSource` 和 `feedRequestId`；任一归因字段缺失时不得声明漏斗与推荐归因闭环完成。
- 点击本地 suggest hit、点击“搜索网络结果”、切换结果 Tab、点击 result hit、点击相关搜索词、点击 `小趣` citation 均必须保留 query/session/request 关联，避免搜索词热力、Feed 推荐归因和 AB 分析断链。
- 统一全屏搜索首页初始态、实时联想态（suggest 本地）与独立网络结果页（result 云侧）。
- 跨 `circle.group` 与 `circle.circle` 的聚合分区显示“讨论”，消息 group 显示“群聊”，Circle 对象显示“圈子”；内部分类投影仍由 Circle 域提供。
- 全局搜索必须是唯一允许的全屏全局浮层。
- 联想页中的“人”结果统一表达为“联系人”，点击目标是会话而不是用户主页中间页。

## 6. 契约与依赖

- 上游能力：[`global-search-experience`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 两阶段跨域搜索旅程 SIT（suggest 本地 + result 云侧）

- GIVEN 执行“两阶段跨域搜索旅程 （suggest 本地 + result 云侧）”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“两阶段跨域搜索旅程 （suggest 本地 + result 云侧）”对应动作。
- THEN suggest 阶段本地快速检索按 联系人/聊天记录/已加入圈子/已关注地点/已关注的人/推荐搜索词 组织，无命中分组隐藏；本地对象不进 result。
- THEN result 阶段固定 Tab 小趣/全部/交集/图片/视频/长文，最终结果只来自云侧；全部 Tab 承载用户分区、实体顶卡与内容流。
- THEN Tag 明确作为 filters.tags 过滤维度，不作为独立结果对象或结果 section；动态筛选首批设计只开放 location/circle 云侧 facet。
- THEN 最近搜索记录 query+launch_context+category_context+timestamp，本地+云同步，支持管理态删除/清空。
- THEN 远端降级/能力受限时由 degradeSignals 驱动降级横幅；单域失败只显该域降级，不阻塞整页。
- THEN 搜索默认页/结果页曝光、停留、referralSource、feedRequestId 归因链可观测。
- THEN 搜索专有事件按 requestId 形成提交/非空或零结果/点击/筛选/非空结果停留漏斗，原始 query、objectId、userId 不进入产品遥测。
- THEN 三项黄金指标在 SLS 聚合、大盘和至少 100 样本告警中同源：有效搜索成功率 ≥35%、首个可操作结果 P95 ≤1.5s、结果到有效行动率 ≥20%。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 Gamma Remote 搜索旅程与黄金指标实证

- 类型：`external_blocker`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：local_contract、真实 Mongo/ES api_integration 与 production
  Remote Patrol 目标均已具备；Gamma-local 日志 Port 替身由统一材料器提供，不要求
  真实 SLS 租户或凭据。当前仍缺真机 CaseResult 与同源指标样本；编译成功、
  Alpha/Mock 或无同源 CaseResult 的 local-gamma 运行均不构成 Remote UAT 和 SLO 证据。
- 目标：使用 Gamma production Remote composition 完成搜索结果、清空本地缓存后
  `RecentSearchState` 回读，并采集同源 `runtime.log.sink` 搜索漏斗与黄金指标样本。
- 完成判定：`cross_domain_search_remote_journey` 在真实设备通过并产出 CaseResult；
  有效搜索成功率、首个可操作结果 P95、结果到有效行动率达到 `SIT-001` 阈值，
  且证据可回溯到同一 requestId/traceId。
