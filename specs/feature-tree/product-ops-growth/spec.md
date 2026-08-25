# L1 Domain Service：product-ops-growth（运营横切） (`product-ops-growth`)

> 一句话定位：建立产品运营侧的事件采集、实验分桶、反馈评估与策略优化闭环。

## 1. 目标与用户价值

建立产品运营侧的事件采集、实验分桶、反馈评估与策略优化闭环。

## 2. 领域边界

### 本领域拥有

- 拥有产品行为事件、实验定义与分桶事实、运营反馈、策略建议、控制面审计事实、账号治理 case/review/decision/执行投递回执，以及面向 App 恢复的各平台当前已发布版本与官方恢复路由事实的生命周期与写入决定权。
- 只能通过本领域公开 command 修改其拥有事实。

### 本领域不拥有

- 不拥有其他 L1 的事实；跨域协作必须使用对方公开 command、query、projection 或 event。
- 不复制 metadata 中的字段、path、错误码和 wire 语义。

### 上下游协作

- 上游：AppRoot Journey 与公开输入事实。
- 下游：直接 L2 能力以及协作 L1 的公开结果。
- 跨域写入：目标领域公开 command；禁止直写目标存储。
- 跨域读取：目标领域公开 query/projection。
- 账号治理协作：Product Ops 只生产经双签的 Suspend/Restore decision 并可靠调用 UserAccount；账号状态、auth epoch、session revoke 与终态事件仍由 User 领域拥有。

## 3. Journey / Scenario 职责

- [`JNY-002 / SCN-005`](../spec.md#scn-005)
  - 本领域负责：在“原生首帧、Flutter 启动恢复与启动遥测”中，按平台与客户端显式 Build 提供当前已发布版本和官方恢复路由事实，并接收脱敏恢复异常与启动事件形成可查询结果。
  - 进入条件：`runtime` 已交付其公开结果。
  - 交付给下游的结果：返回可信版本/PWA/APK/Web 恢复事实，并将脱敏异常与启动事件写入环境绑定的唯一观测端口。
  - 不负责：不拥有客户端启动、致命异常判定或主容器重建状态，也不以指标、缓存或本地推断替代已发布版本事实。
- [`JNY-004 / SCN-001`](../spec.md#scn-001)
  - 本领域负责：在“写文字创建、可靠发布与结果回流”中，接收脱敏事件与归因事实，形成可查询指标、实验或渠道转化结果。
  - 进入条件：`runtime` 已交付其公开结果。
  - 交付给下游的结果：接收脱敏事件与归因事实，形成可查询指标、实验或渠道转化结果，形成该场景中本领域负责的终态。
  - 不负责：不修改业务对象，也不以指标或建议替代业务成功事实。
- [`JNY-004 / SCN-002`](../spec.md#scn-002)
  - 本领域负责：在“照片创建、像素编辑、原图可靠上传与发布回流”中，接收脱敏事件与归因事实，形成可查询指标、实验或渠道转化结果。
  - 进入条件：`runtime` 已交付其公开结果。
  - 交付给下游的结果：接收脱敏事件与归因事实，形成可查询指标、实验或渠道转化结果，形成该场景中本领域负责的终态。
  - 不负责：不修改业务对象，也不以指标或建议替代业务成功事实。
- [`JNY-004 / SCN-003`](../spec.md#scn-003)
  - 本领域负责：在“视频创建、转码处理、发布与结果回流”中，接收脱敏事件与归因事实，形成可查询指标、实验或渠道转化结果。
  - 进入条件：`runtime` 已交付其公开结果。
  - 交付给下游的结果：接收脱敏事件与归因事实，形成可查询指标、实验或渠道转化结果，形成该场景中本领域负责的终态。
  - 不负责：不修改业务对象，也不以指标或建议替代业务成功事实。
- [`JNY-010 / SCN-023`](../spec.md#scn-023)
  - 本领域负责：在“对象对外分享分发”中，接收脱敏事件与归因事实，形成可查询指标、实验或渠道转化结果。
  - 进入条件：用户发起“对象对外分享分发”且身份、输入与权限前置成立。
  - 交付给下游的结果：接收脱敏事件与归因事实，形成可查询指标、实验或渠道转化结果，供 `discovery-content` 继续处理。
  - 不负责：不修改业务对象，也不以指标或建议替代业务成功事实。

## 4. 业务能力

- [`event-ingestion-and-analytics`](./event-ingestion-and-analytics/spec.md)：App 产品事件/异常、受限启动诊断、Elasticsearch 明细/聚合、Portal 查询和推荐反馈边界的端到端验收。
- [`experiment-bucketing-and-rollout`](./experiment-bucketing-and-rollout/spec.md)：推荐/搜索服务端权威分桶、实际流量事实归因，以及未绑定 Product Ops 控制面的 fail-closed 单轨验收。
- [`feedback-optimization-loop`](./feedback-optimization-loop/spec.md)：反馈优化大循环：行为反馈 → 兴趣/人群画像派生 → 元数据驱动的推荐策略解析与自调建议 → 人审发布。算法侧闭环（content 派生 + user 投影 + recpolicy 热加载引擎 + 顾问 suggest-only）。
- [`outbound-share-distribution`](./outbound-share-distribution/spec.md)：5 类对象统一对外分享分发（微信卡片/海报/口令/系统分享），携带归因并可靠回流。
- [`product-control-plane-foundation`](./product-control-plane-foundation/spec.md)：统一产品事件、实验、反馈优化与发布治理

## 5. 领域要求

<a id="req-001"></a>
### REQ-001 product ops growth 领域边界验收

- 领域边界、上下游依赖、工程映射和服务治理清晰。

<a id="req-002"></a>
### REQ-002 作为统一 Web 门户 `ops-portal` 中 `Product Ops` 工作域的特性树承载层

- 作为统一 Web 门户 `ops-portal` 中 `Product Ops` 工作域的特性树承载层。
- 冻结统一运营控制面的两大模块：`治理处置` 与 `增长/实验/推荐运营`。
- 运营事件必须统一 schema，禁止各模块自由扩展核心字段语义。
- 实验发布必须具备审计、灰度、回滚链路。
- 运营链路必须可关联 request/trace/page/session。
- 用户增长链路必须区分 `OwnerAccount` 管理视角与 `Persona` 应用视角：
- 面向 `product-ops` 的管理接口必须从统一控制面元数据生成，禁止手写临时运营后台接口。
- 推荐运营范围必须覆盖召回、粗排、精排的受控干预，而不是仅限 AB 实验。
- 审核、处罚、申诉、恢复必须支持工作流、证据、SLA 与双签审计。
- 用户发展、邀请传播、通讯录发现、分群经营、恢复治理必须支持跨域审计与生命周期视图。
- 账号治理必须由具名 `AccountEnforcementCase` 聚合承载，moderation/appeal 共享审批与投递机制但动作显式；禁止 generic workflow Document、直写 User、双发送或两套恢复状态机。

## 6. 领域验收

<a id="dom-001"></a>
### DOM-001 product ops growth 领域边界验收

- 条件：本领域收到有效输入且前置领域事实成立。
- 可观察结果：领域边界、上下游依赖、工程映射和服务治理清晰。
- 禁止结果：不得绕过本领域公开 command/query/event 写入其拥有事实。

## 7. 工程归属

- App：`quwoquan_app/lib/service/product_ops_service`
- App（协作引用，不用于代码归属）：`quwoquan_app/lib/service/content_service`、`quwoquan_app/lib/service/assistant_service`
- Contracts（协作引用，不用于代码归属）：`quwoquan_service/services/product-ops-service/contracts`、`quwoquan_service/services/recommendation-service/contracts`
- Service：`quwoquan_service/services/product-ops-service`
- Service（协作引用，不用于代码归属）：`quwoquan_service/services/recommendation-service/internal/recommendation/recommendation_model_release/infrastructure/model_runtime`
- 测试：
  - `local_contract`：`quwoquan_service/services/product-ops-service`
  - `api_integration`：`quwoquan_service/services/product-ops-service`
  - `user_acceptance`：`quwoquan_ops/tests/acceptance/user_acceptance`、`quwoquan_app/test/user_acceptance/journeys/account_enforcement`、`quwoquan_app/test/user_acceptance/journeys/event_ingestion`、`quwoquan_app/test/user_acceptance/journeys/event_reliability_replay`

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 product ops growth 领域边界验收

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：领域边界、上下游依赖、工程映射和服务治理清晰。
- 完成判定：`DOM-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 访客身份不被访问记录边界接受，首页出现访客验证失败提示

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：当前 `RecordVisit` 的可信 actor 派生要求 principal 携带 `PersonaID` 或 `DeviceActorID`，二者皆空即拒绝。
- 影响或价值：App 以 guest session 调用该 command 时被判为认证失败，首页顶部持续显示"我们没能完成本次访客验证"。
- 影响或价值：该 command 的 `authMode` 允许访客，因此这是访客身份在服务边界未被承认，而不是访客不该调用。
- 影响或价值：alpha 本地实测 `POST /ops/visits` 无凭据返回 `GATEWAY.USER.unauthorized`，路由本身可达。
- 完成判定：`DOM-001` 对应行为满足，允许访客的 command 在只有设备级身份时也能派生可信 actor，并由 api_integration 覆盖访客与登录两种身份
