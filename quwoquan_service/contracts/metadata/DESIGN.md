# 业务对象元数据设计总览

> 唯一真相源。所有代码生成（Go + Dart + Python）均从本目录 YAML 驱动。
> 修改 YAML → `make verify` → `make codegen` → `make codegen-app` → `make gate`。

---

## 目录结构

```
contracts/metadata/
├── _shared/                       # 跨域共享（真正无所有者的内容）
│   ├── types.yaml                 # 枚举 + 通用类型（ContentType/Visibility 等）
│   ├── redis_keyspace.yaml        # Redis key 命名格式规范
│   ├── test_infra.yaml            # 测试引擎配置（engines/mocks/data_management）
│   ├── openapi_common.yaml        # OpenAPI 公共组件（securitySchemes/parameters）
│   └── envelope.schema.json       # 消息信封 JSON Schema（MQ/事件总线）
│
├── _vectors/                      # 向量索引（跨多服务消费，保持独立）
│   ├── content_embedding.yaml     # Post 内容语义向量（推荐 + 助手检索）
│   └── user_context_embedding.yaml# 用户上下文向量（个性化推荐）
│
├── content/                       # 域：内容 → content-service
│   ├── openapi.yaml               # HTTP 接口契约（对外快照）
│   └── post/                      # 聚合根 Post
│       ├── aggregate.yaml         # 存储后端 + counter strategy + DDD映射
│       ├── fields.yaml            # 字段定义 + 分类（PUBLIC/PII/SENSITIVE/SECRET）+ 日志策略
│       ├── storage.yaml           # 索引 + Migration DDL + TTL
│       ├── events.yaml            # 领域事件 + 消费方 + ML信号
│       ├── service.yaml           # API 路由（仅路由声明）
│       ├── projections/           # 端侧视图（紧靠实体，codegen → Dart DTO）
│       │   ├── discovery_feed.yaml
│       │   ├── photo_post.yaml
│       │   ├── video_post.yaml
│       │   ├── article_post.yaml
│       │   └── moment_post.yaml
│       ├── errors.yaml            # 域错误码（codegen → Dart enum + Go 常量）
│       ├── behaviors.yaml         # 行为采集 + 推荐特征 + 训练样本
│       ├── privacy.yaml           # 隐私策略（端侧日志过滤 + GDPR 删除级联）
│       ├── ui_config.yaml         # 端侧 UI 配置（tab/布局/feature flags，codegen → Dart）
│       └── tests/                 # 三层测试契约（测试代码的声明性规范）
│           ├── mock.yaml          # 端侧独立（flutter test，不依赖云）
│           ├── contract.yaml      # 云侧独立（go test，真实 DB）
│           └── e2e.yaml           # 端云集成（staging，advisory）
│
├── user/                          # 域：用户 → user-service
│   ├── openapi.yaml
│   ├── user_profile/
│   │   ├── aggregate.yaml  fields.yaml  storage.yaml  events.yaml  service.yaml
│   │   ├── projections/user_profile_view.yaml
│   │   ├── errors.yaml  privacy.yaml
│   │   └── tests/{mock,contract,e2e}.yaml
│   ├── follow_edge/
│   │   └── entity.yaml  fields.yaml  storage.yaml  events.yaml  service.yaml
│   └── block_edge/
│       └── entity.yaml  fields.yaml  storage.yaml  events.yaml  service.yaml
│
├── messages/                      # 域：即时通讯 → chat-service
│   ├── openapi.yaml
│   └── conversation/
│       ├── aggregate.yaml  fields.yaml  storage.yaml  events.yaml  service.yaml
│       ├── projections/chat_inbox.yaml
│       ├── errors.yaml
│       └── tests/{mock,contract,e2e}.yaml
│
├── social/                        # 域：社交 → circle-service + social graph
│   ├── openapi.yaml
│   └── circle/
│       ├── aggregate.yaml  fields.yaml  storage.yaml  events.yaml  service.yaml
│       ├── projections/circle_feed.yaml
│       ├── errors.yaml
│       └── tests/{mock,contract,e2e}.yaml
│
├── assistant/                     # 域：AI 助手 → assistant-service/orchestrator
│   ├── assistant_run/
│   │   └── aggregate.yaml  fields.yaml  storage.yaml  events.yaml  service.yaml
│   └── skill_consent/
│       └── entity.yaml  fields.yaml  storage.yaml  events.yaml  service.yaml
│
├── recommendation/                # 域：推荐 → rec-model-service
│   ├── openapi.yaml
│   ├── model_release/
│   │   └── aggregate.yaml  fields.yaml  storage.yaml  events.yaml  service.yaml
│   ├── intersection_visit_state/
│   │   └── entity.yaml  fields.yaml  storage.yaml  events.yaml  service.yaml
│   └── rec_model/
│       ├── entity.yaml  fields.yaml  storage.yaml  events.yaml  service.yaml
│       └── projections/{recommend_feature,training_samples,learning_events,model_registry}.yaml
│
├── notification/                  # 域：通知 → notification-service
│   ├── openapi.yaml
│   └── notification/
│       └── entity.yaml  fields.yaml  storage.yaml  events.yaml  service.yaml
│
└── ops/                           # 域：运营/平台 → ops-service
    ├── openapi.yaml
    ├── experiment/
    │   └── aggregate.yaml  fields.yaml  storage.yaml  events.yaml  service.yaml
    ├── experiment_assignment_fact/
    │   └── entity.yaml  fields.yaml  storage.yaml  events.yaml  service.yaml
    └── visit_record/
        └── entity.yaml  fields.yaml  storage.yaml  events.yaml  service.yaml
```

---

## 每个实体目录的文件职责

| 文件 | 职责 | codegen 产出 |
|---|---|---|
| `aggregate.yaml` | 存储后端、DDD 分层映射、counter strategy | Go aggregate 骨架 |
| `fields.yaml` | 字段语义 + 分类 + 日志策略 | Go struct + Dart DTO + Migration |
| `storage.yaml` | 索引 + Migration DDL + TTL | Go migration 文件 |
| `events.yaml` | 领域事件 + 消费方 + 信号标注 | Go events.go |
| `service.yaml` | API 路由（仅路由声明） | Go routes + Dart 路由常量 |
| `projections/*.yaml` | 端侧视图投影（字段映射 + alias） | Dart typed DTO（DO NOT EDIT） |
| `errors.yaml` | 结构化错误码（MODULE.KIND.REASON） | Dart ErrorCode enum + Go 常量 |
| `behaviors.yaml` | 行为采集 + 推荐特征 + 训练样本 | Dart BehaviorTracker + Python Pydantic |
| `privacy.yaml` | 端侧日志 mask + GDPR 删除级联 | Dart PrivacyPolicy.sanitizeForLog() |
| `ui_config.yaml` | tab/布局/feature flags 配置 | Dart UIConfig（DO NOT EDIT） |
| `tests/mock.yaml` | 端侧独立测试场景声明 | Dart 测试骨架（flutter test） |
| `tests/contract.yaml` | 云侧契约测试场景声明 | Go 测试骨架（真实 DB） |
| `tests/e2e.yaml` | 端云集成测试场景声明 | staging CI 测试 |

---

## codegen 流水线（全量）

```
make codegen-openapi          # ContractGraph -> 各域 OpenAPI 生成快照（原子替换）
make codegen-contract-graph   # 先生成 OpenAPI，再固化 generated/contract_graph.json
make verify-openapi           # 直接比较磁盘快照与 ContractGraph 期望
make verify-metadata          # YAML 内部一致性（枚举引用/字段类型/路径绑定）
make codegen                  # OpenAPI + Go struct/routes/errors/migration/fixture
make codegen-app              # Dart: DTO + metadata + errors + behaviors + privacy + ui_config
make codegen-rec-model-python # Python: features + training_samples（Pydantic）
```

---

## 门禁扩展（G0~G10）

| 门禁 | 检查内容 |
|---|---|
| G1 | metadata YAML 内部一致性 |
| G2 | codegen 产物 hash 保护（DO NOT EDIT 文件未被手改） |
| G3 | DDD 层级导入约束（domain ← application ← adapters ← infrastructure） |
| G4 | 错误码覆盖：errors.yaml 中每个 code 在 tests/ 至少有一个场景 |
| G5 | 行为路由一致：behaviors.yaml batch_route ⊆ service.yaml api_routes |
| G6 | UI 配置完整：ui_config.yaml contentType ⊆ fields.yaml ContentType 枚举 |
| G7 | 测试场景覆盖：tests/contract.yaml scenarios ⊆ Go 测试函数（按命名约定） |
| G8 | 隐私策略覆盖：PII/SENSITIVE 字段在 privacy.yaml 有声明 |
| G9 | 行为类型合法：behaviors.yaml events.type ⊆ _shared/types.yaml BehaviorEventType |
| G10 | 投影路径一致：projections/*.yaml output_path 前缀与所在域名称匹配 |

---

## 设计原则

1. **业务对象优先**：目录以域/实体组织，不以技术类型（metadata/openapi/projections）组织
2. **就近原则**：投影、错误码、测试声明紧靠它们的来源实体，不设全局目录
3. **无兼容路径**：0→1 构建，codegen 工具只识别规范路径，不存在 fallback
4. **声明即契约**：tests/*.yaml 是测试意图的声明；`make gate` 验证测试代码实现了全部声明场景
5. **端云对称**：一个域目录 = 一个领域服务 = app cloud/{domain}/ 目录

## D0 对象模型冻结

### Actor

- `UserAccount` 是账号/认证/安全聚合；`Persona` 是公开业务主体。
- `CredentialBinding` 因 provider subject 唯一、callback 并发和独立撤销而成为独立聚合。
- `ActorContext` 只允许 `accountId`、`personaId`、`deviceActorId`；operation 必须声明所需 actor。
- 公开作者、关系、互动、创作归 `personaId`；认证、凭证和安全归 `accountId`；游客事实归 `deviceActorId`。

### 当前 aggregate.yaml 处置

- `Post`：保留生命周期根；Comment、ContentReaction、MediaUploadSession、MediaAsset、PostModerationCase、Report 拆为独立聚合；站外分享归 `OutboundShareFact`，圈内分发归 Circle 的 `CirclePostPlacement`。
- `CallSession`：保留；`CallParticipant` 最多 32 个，可作为有界成员。
- `Connection`：改为 `runtime_session`；Presence 是 projection，不计业务聚合。
- `ExternalInteraction`：保留可靠外部交互工作流；Sms/Push 是类型化 interaction，不另占 ledger。
- `UserAccount`：只拥有账号状态；Persona、AuthenticationChallenge、CredentialBinding、AccountSession、DeviceRegistration、UserSettings、ProfileUpdateProposal 均是独立生命周期根。
- `Conversation`：只拥有会话身份、策略和 bounded metadata；Message、Membership、UserState、Receipt 按独立写模型治理。
- `Circle`：只拥有社区主档和治理策略；CircleGroup、Membership、Activity、File/Placement 独立。
- `Homepage`：保留主档和 published/offline；Claim、StatusReport、Review 独立，Shell/Summary/RelatedGroups 是 Slice。
- `AssistantRun`：AssistantConversation、AssistantRun、SkillSubscription、SkillConsent 为独立根；AssistantTurn 是投影，ProfileUpdateProposal 归 User，InteractionEvent/Scorecard 为追加事实。
- `SearchQuery`：改为 request/append-only query fact；执行由 SearchFacade + named Reader 完成。
- `Location`：改为 external query capability，LocationPoi 为 value/read model。
- `SmsOtp`：OTP challenge 归 User/Auth；integration 只拥有 ExternalInteraction。
- `PushDelivery`：是 Notification 意图对应的 ExternalInteraction，不拥有业务生命周期。

### 当前 entity.yaml 处置

- `CreatorRuntimeProfile`、`UserLifeItem`、`UserWork`：imported/materialized projection。
- `ModelScoreRequest`：仅是 `RecommendationModelRelease` scoring Reader 的 inference wire DTO，不登记为业务对象、聚合或生命周期 owner。
- `Report`：governance aggregate。
- `DeletedPostTombstone`：内容删除后的 retention/audit 事实，由 Post 删除事件创建；
  不恢复 Post 生命周期，不作为可编辑业务聚合。
- `TagNodeView`：由版本化 `TagTaxonomyRelease` 激活事件构建的只读投影；节点集合不进入聚合一致性边界。
- `PersonaRelationship`：以规范化 persona pair 为 ID 的关系聚合，最多拥有两个 `RelationshipDirection` 子对象；follow/block 在 PostgreSQL 同一事务内迁移，block 原子清除双方 follow，unblock 不恢复。删除独立 `FollowEdge`、`BlockEdge` 生命周期。
- `SubjectFollow`：Persona 对 Homepage/Place 等非 Persona 公开主体的关系聚合；删除 `HomepageFollow` 重复生命周期，Homepage 只消费计数与 viewer Slice。
- `HomepageClaimRequest`、`HomepageStatusReport`、`HomepageReview`：各自拥有申请、审核或评价生命周期的独立聚合，通过 homepageId 引用 Homepage。
- `FollowingSubject`：关系组合 projection；私有 visit watermark 由独立聚合 `FollowedSubjectVisitState` 承载，与 Recommendation 的 `RecommendationIntersectionVisitState` 区分。
- `InviteRecord`、`GreetingRequest`、`ContactDiscoveryRecord`：独立 workflow aggregate。
- `VisitRecord`、`EventRecord`、`ChannelIngressReceipt`：append-only fact；其中 `ChannelIngressReceipt` 只负责外部渠道验签去重后的不可变接收事实。
- `TagFeedback`：只追加反馈事实，不修改 TagTaxonomyRelease 或 TagNode。
- `Experiment`：实验定义与发布生命周期根；`ExperimentAssignmentFact` 是确定性、幂等、不可修改的分配事实。
- `Notification/AppMessage`：拥有 create/deliver/ack/read/dismiss 的 aggregate。
- `SkillConsent`：拥有 grant/revoke/version/audit 的 aggregate。
- `_control_plane/domains/entity.yaml` 是控制面部署目录，不参与业务对象数量。

### Post 样板关键裁决

- Moderation decision 绑定 `postId + postVersion + contentDigest`；编辑立即使旧 approval 失效。
- 每条 Comment 是独立聚合，首发 thread 深度上限 2；Post 只保存可选 `pinnedCommentId`。
- Reaction 以 `target + actor + reactionType` 唯一；站外分享追加 OutboundShareFact，引用发布创建 Post，圈内转发创建 CirclePostPlacement；Report 是治理 Case。
- MediaUploadSession 有 TTL，完成后产生 MediaAsset；Post 只保存有序 mediaAssetId。
- 已知删除在 retention 内 410，隐私删除先脱敏，硬清除后 404；投影由删除事件收敛。
- Post Query 只拥有 detail/card/presentation/author-page；Feed/Search/Intersection/Impact/Footprint 各归其 query owner。
- UGC 与 Data/PGC 只通过 `BulkImportFacade` 汇入同一 command/event pipeline，禁止直写业务表或 projection。

## ContractGraph 两层接口

每个 public/internal operation 必须编译成唯一 `OperationDescriptor`：

```yaml
operation_id: content.post.PublishPost
transport:
  method: POST
  path_template: /content/posts/{postId}:publish
application:
  facet: PostCommandFacade
  method: publish
  kind: command
  aggregate_owner: Post
actor:
  requires: persona
storage:
  authoritative_port: PostStore
errors:
  catalog: content/post/errors.yaml
```

HTTP `path_template` **禁止**协议版本段（`/v` + 数字、`/internal/v` + 数字、
`/callbacks/v` + 数字）；只允许无版本资源路径，例如 `/content/feed`、
`/internal/recommendation/model-releases:score`。健康探针 `/health` `/healthz`
`/metrics` `/livez` `/startupz` 除外。门禁：
`make verify-api-path-unversioned`（已挂入 `gate_repo.sh`）。

Query operation 将 `kind` 设为 `query`，并声明 `reader` 与 `slice`；禁止仅用 URL、DTO 名或 Handler 名推断。
Append-only fact 的 POST command 必须声明 `append_sink`，且不得伪装成
`aggregate_owner`；编译器强制两者互斥，并验证目标分别为 `append_only_fact` 与
`aggregate_root`。

### Object Application Facade

- Command facet：authz、幂等、load aggregate、领域行为、commit + outbox。
- Query facet：调用 named Reader 返回 typed Slice，不加载聚合。
- 一个 facet 不超过 10 个方法；超过即按子域/场景拆分。
- transport adapter 不依赖 infrastructure；跨域只经 ExternalDomainPort、事件或本地 projection。

operation 的 `reliability.idempotency` 只描述请求重放；调用方版本前置条件由可选
`concurrency.version_precondition: if_match` 表达。未声明时禁止业务 command/encoder
发送 `If-Match`。`if_match` 只允许 aggregate-root command，且必须能证明存在真实多写者
快照覆盖；一次创建/发布、关系 set/unset、事实 append、projection、external query 与
runtime session 禁止使用。服务端 Store 的 `ExpectedVersion` 始终是内部 CAS 参数，不是
公开 API 默认字段。

### Object Data Ports

- `AggregateStore` 是对象专属具名接口，至少表达 Load、Commit、内部 expectedVersion、IdempotencyKey 和 outbox。
- Reader 以业务目的命名，例如 `PostDetailReader`、`AuthorPostReader`，不暴露 GenericSliceReader。
- adapter 必须声明 `authoritative`、`projection`、`cache`、`external` 或 `memory`；只有 authoritative store 接受 command commit。
- 跨上下文写入只经目标 Command Facade，读取只经 named Reader/Slice，异步协作只经公开事件与 outbox/inbox；只有已证明补偿语义的具体流程使用专用 process manager，不存在通用 Saga 或分布式 UnitOfWork。
- aggregate members 只允许 owned entity/value object；子对象只能经聚合根访问。需要独立命令、版本、并发或生命周期即为 aggregate root，不得为方便直连子对象 Store/Repository。
- Mongo/PG 中 aggregate change 与同库 outbox 单事务；消费者以 inbox/checkpoint 保证幂等和 replay。

最小机制矩阵固定为：aggregate 内部 CAS；owned entity 继承 owner；value object 无版本；
append-only fact 唯一 dedupe；projection 每 source 单调 version/sequence；external reference
无本地写并发；runtime session 逐连接 lease/fencing。禁止为了统一接口给后五类补
`expectedVersion` 或 command receipt。

## OpenAPI 派生快照

`service.yaml api_routes` 编译出的 `ContractGraph.Operations` 是 HTTP transport
唯一真相源。`contracts/metadata/{domain}/openapi.yaml` 只是确定性生成快照，
禁止手写、合并旧内容或保留未知路径。生成器覆盖 `/`、`/internal/` 与
`/callbacks/` 下的全部 operation，并固定输出：

- `operationId` 使用域内稳定 `LocalID`，同时写入 canonical
  `x-contract-operation-id`。
- `x-object-id`、`x-actor`、`x-application` 直接来自同一个
  `OperationDescriptor`，command 输出 aggregate owner，query 输出 reader/slice。
- URL 模板中的每个 `{parameter}` 都生成 required path parameter。
- `RequestEntity`、`ResponseEntity`、`ResponseBody` 与 `ResponseBodyKind`
  决定 request/response；`page` 生成类型化 items + cursor 结构，`ack` 生成
  `204`，其他实体通过命名 component 引用。
- `_shared/openapi_common.yaml` 继续提供 `ErrorResponse` 与 bearer security
  component，域快照仅通过 `$ref` 复用。

当前 ContractGraph 尚未携带 fields/projection 的完整字段 AST 时，生成器必须
输出带 `x-contract-entity` 与 `x-contract-placeholder` 的命名 component。
禁止用 `additionalProperties: true` 或匿名 Map 伪造业务 schema。具体字段仍以
`fields.yaml` / projection codegen 为真相，后续只能扩展 compiler AST 后再增强
OpenAPI schema，不能另写第二套 parser 或让 transport operation 缺席。

`generate-openapi` 会先生成全部内容，在各目标目录写入临时文件并逐文件原子
rename，随后删除 ContractGraph 已不存在的孤儿域快照；不存在 merge/preserve
模式。`check-openapi` 必须直接读取磁盘 artifact，与期望字节全等比较，missing、
stale、orphan 任一情况均失败。标准顺序是：

```text
qwq-contract generate-openapi
  -> qwq-contract generate
  -> qwq-contract check-openapi
  -> qwq-contract validate --profile commercial
```

## 严格 compiler 与统计

唯一流水线为：

```text
_schemas
  -> internal/metadata/ast
  -> internal/metadata/load
  -> internal/metadata/validate
  -> internal/metadata/graph
  -> internal/metadata/codegen
  -> tools/qwq_contract
```

`qwq-contract validate/generate/check/generate-openapi/check-openapi/coverage`
驱动所有语言产物。未知字段、旧字段、重复 ID、缺
owner/Slice/store/error/actor/test contract 直接失败。对象、operation、事件和
覆盖数量只能由 ContractGraph 生成，文档不得手工维护。
