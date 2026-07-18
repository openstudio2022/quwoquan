# 应用根设计

## 设计目标

应用根设计定义全 App 的长期架构和治理约束，确保产品规格、领域服务、业务能力、Story、代码工程和测试工程使用同一套概念。

## 全局分层

```text
产品与验收层
  AppRoot Journey / Scenario / UAT

领域服务层
  L1_domain_service

业务能力层
  L2_business_capability

最小价值层
  L3_story / GWT / contract

工程实现层
  quwoquan_app / quwoquan_service / quwoquan_data / quwoquan_ops

契约与测试层
  contracts/metadata / local_contract / api_integration / user_acceptance
```

## 全局职责边界

- 应用根负责跨领域编排、UAT、全局架构、技术约束、观测、灰度和回滚。
- 领域服务负责 bounded context、产品领域边界、上下游依赖、服务治理和运行约束。
- 业务能力负责领域内状态、策略、数据流、端云协同和 SIT。
- Story 负责最小价值点、GWT、接口契约和最小测试证据。

## 工程映射

领域服务必须映射到以下工程资产：

- App UI：`quwoquan_app/lib/ui/{domain}`。
- App cloud：`quwoquan_app/lib/cloud/services/{domain}` 与 generated runtime。
- Metadata：`quwoquan_service/contracts/metadata/{domain}`。
- Service：`quwoquan_service/services/*-service`。
- Deploy：`quwoquan_ops/environments/process_domain_mapping.yaml` 等部署映射。
- Test：`quwoquan_app/test/**`、`quwoquan_service/services/*/tests`、metadata tests。

## 技术约束

- metadata 是字段、错误码、路径、operation、surface、route 的唯一真相源。
- App UI 不直接依赖 mock 数据，必须通过 Provider / Repository。
- Go 服务遵循 DDD 分层：`domain <- application <- adapters <- infrastructure`。
- 测试工程层只使用 `local_contract`、`api_integration`、`user_acceptance`。
- `树内计划文档`、`树内任务文档`、Story 设计文档 不再是正式治理文档。

## D0 业务对象架构冻结

### Actor 与对象分类

- `UserAccount` 只承担账号、认证和安全；`Persona` 是公开业务主体。
- `ActorContext.accountId` 只用于认证/安全，`personaId` 用于公开业务动作，`deviceActorId` 用于游客事实。
- 业务对象只允许 `aggregate_root`、`owned_entity`、`value_object`、`projection`、`external_reference`、`append_only_fact`、`runtime_session` 七类；`separate_aggregate` 不是输入别名而是非法值。
- 无界集合、高并发独立生命周期和跨存储对象不得伪装成聚合成员。
- 每个 domain 必须由唯一 `business_object_map.yaml` v3 登记稳定 context id、对象身份/版本、owner、存储角色、mutation/event 入口、访问策略、关系字段和生命周期；未登记 domain/object 或关系字段不守恒直接阻断 commercial ContractGraph。
- owned entity/value object 只能经所属聚合根寻址、修改和投影读取；需要独立命令、版本、并发控制或生命周期的对象必须提升为 aggregate root。

### 两层端云接口

第一层是 Object Application Facade：

- transport 只调用对象的细粒度 command/query facet。
- command 负责 authz、幂等、装载聚合、领域行为和提交。
- query 直接调用具名 Reader 返回 typed Slice。
- Facade 是统一命名空间，不是超过 10 个方法的上帝接口。

第二层是 Object Data Ports：

- `AggregateStore` 负责一个聚合版本变更与同库 outbox 原子提交。
- 具名 Reader 负责详情、列表、搜索、统计和页面 Slice。
- ExternalDomainPort 使用本域 ACL DTO，禁止跨服务直连数据库。
- cache、ES、远端 API 不能冒充 authoritative write store。

跨聚合写入只调用目标上下文公开 Command Facade；跨聚合读取只调用 named Reader/typed Slice；异步协作只消费公开事件并使用 outbox/inbox。只有存在已证明补偿语义的具体业务流程才允许专用 process manager，不建设通用 Saga，也不使用分布式 UnitOfWork。

### 统一 URL

- App 只消费 `CloudRuntimeConfig.gatewayBaseUrl` 与 generated client。
- 公共 API 统一为 `/{domain}/{resource}`；状态迁移使用 `POST .../{id}:{action}`。
- 内部 API 使用 `/internal/**`，第三方回调使用 `/callbacks/**`，公开分享/SEO URL 独立于 API。
- URL 嵌套只表达导航/过滤，不推断聚合 owner。
- method/path/operation/route/surface/page 是不同标识，禁止字符串复用和第二映射。

### Actor、对象与样板关键裁决

- Relationship 使用按无序 persona pair 定位的 `RelationshipPair`，内部保存双方定向 Follow/Block；Greeting/Invite/ContactDiscovery 独立。
- CredentialBinding 独立于 UserAccount，以保证 provider subject 唯一和 callback 并发。
- PostModerationCase 绑定 `postId + postVersion + contentDigest`；内容编辑使旧审批失效。
- Comment、Reaction、MediaUploadSession、MediaAsset、Report 都是 Post 之外的独立聚合。站外分享是 `OutboundShareFact`；引用发布创建新 Post；圈内分发由 Circle 的 `CirclePostPlacement` 拥有，Content 不保留 `ShareRecord` 或 `PostDistribution` 第二生命周期。
- Post 只提供 detail/card/presentation/author-page；Feed、Search、Intersection、Impact/Footprint 由各自 query owner 提供。
- Data/PGC 只经签名 BulkImportFacade 进入与在线一致的 command pipeline，禁止直写业务表或 projection。
- Mongo/PG authoritative store 必须把 aggregate change 与 outbox 放入同一事务。
- CircleGroup 只表示 Circle/组织节点群；ad-hoc 群属于 Conversation。
- Connection 只计 runtime session，Presence 是 projection。

### 公共基础设施边界

公共层只允许 ContractGraph compiler、operation context、RuntimeFailure/RecoveryPolicy/ErrorResponse、HTTP、config、observability、typed messaging、governance、health、clock/id、platform capability 和纯展示基础组件。

禁止公共化：

- `Repository[T]`、GenericAggregateStore、BaseFacade、GenericSliceReader。
- 业务命令、审核/发布/互动 policy、ACL DTO、万能页面/Provider/ViewModel。
- 在 content Post+Report 样板和两种真实 store adapter 通过前提炼 scaffold。

### 页面与体验

- 每个页面绑定唯一 page/route/surface、experience owner、data owner、typed params、Query Slice、auth/capability 和 telemetry descriptor。
- 页面边界只能接收一种 canonical presentation Slice。
- 所有页面必须覆盖 light/dark、高对比度、语义 token、320/390/768/1024/1440 响应式、无障碍、2.0 字体、reduce motion 和 capability 降级。
- loading、empty、auth、permission、error、offline、retrying、recovered、append-error 使用公共视觉 primitive；业务文案和 recovery 由领域提供。
- 生产 Router/Shell 不可达的页面必须恢复唯一入口或删除；测试 Router 不计可达。

### 零兼容迁移

同一对象的新 Facade/Store/Slice 上线时，旧 route、Repository、DTO、decoder、Map、状态和测试必须在同一变更中删除。测试环境数据使用 reset/re-import；必须保留的数据只允许一次性离线迁移，运行时不保留 shim、alias、dual-read 或 dual-write。

## 观测与发布治理

应用根设计要求所有可发布能力具备：

- SLO/KPI。
- 行为埋点和归因链。
- 弱网、性能、容量边界。
- 灰度策略和回滚条件。
- `api_integration/user_acceptance` 发布前证据。
