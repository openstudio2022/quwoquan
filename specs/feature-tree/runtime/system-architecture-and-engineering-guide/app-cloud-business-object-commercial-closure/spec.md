# L3：App Cloud 业务对象商用闭环

## 最小价值点

App 通过同一份不可变 ContractGraph，只调用具名业务对象 Facet 和类型化 operation；服务端以可信 principal 执行认证、授权和对象级 BOLA，alpha 与 production 装配物理隔离。任一受影响 Journey 都不再依赖动态 Repository、客户端身份头、Mock fallback 或第二套接口真相源。

## 归属

- 领域服务：`runtime`
- 业务能力：`system-architecture-and-engineering-guide`
- Story：`app-cloud-business-object-commercial-closure`
- AppRoot UAT：`UAT_BUSINESS_OBJECT_COMMERCIALIZATION`
- 关联 Scenario：
  - `identity-entry-persona-continuation`
  - `content-feed-open-detail`
  - `global-search-query-and-filter`
  - `global-route-edge-pop-contract`
  - `message-direct-and-greeting-upgrade`
  - `circle-entity-group-handoff`
  - `assistant-context-grounded-answering`
  - `outbound-object-share-distribution`
  - `intersection-action-deepening-on-object`
  - `profile-share-interaction-history`

## 行为范围

### In Scope

- 业务对象 command owner、query Reader/Slice、Facet、operation 和三层模型边界。
- ContractGraph 固定 bundle、Go 服务端执行 descriptor/guard、Dart operation-specific client。
- 服务端可信 Principal/ActorContext、operation authorization、对象 owner/member/BOLA。
- App Cloud 分层、Remote/alpha adapter、production/alpha composition 与 Mock/fixture 物理隔离。
- deadline、cancel、retry/idempotency、RuntimeFailure、telemetry 与 SLO 合同。
- 十条 Scenario 的 local_contract、api_integration、user_acceptance 和四环境证据。
- clean checkout、generated manifest、AOT/SBOM、灰度与回滚准出。

### Out of Scope

- 替各业务领域决定 aggregate、owned entity、value object 或业务状态机。
- 建设通用 CRUD Repository、运行时 metadata registry、事件溯源框架、分布式事务或通用 Saga。
- 修改推荐算法、内容正文生产算法和 edge-media 内部媒体算法。
- 用本 Story 代替各业务对象自己的 L1/L2/L3 验收。

## 业务对象与读写规则

- 每个 command 只绑定一个 canonical aggregate owner；对象不变量由 domain behavior 执行，application 不直接修改公开字段。
- 每个 query 只绑定一个具名 Reader 与 typed Slice；query 不加载 write aggregate。
- AggregateStore 是对象专属 `Load + Commit` 端口，Commit 原子持久化 state/version、幂等 receipt 与同库 outbox。
- owned entity 不拥有独立 Store；append-only fact 只允许 typed append/dedupe；projection 可重建且只由 projector 写入。
- 读写分离是模型、端口和执行链分离，不强制独立数据库；跨 aggregate/domain 默认 outbox/inbox 最终一致。
- App application coordinator 只组合无需原子一致的少量 capability；稳定排序、统一权限或复用页面 Slice 由服务端 projection owner 提供。

## 端云执行规则

### Command

`generated decoder -> typed command + trusted actor -> Command Facet -> aggregate behavior -> AggregateStore.Commit`

### Query

`generated decoder -> Query Facet -> named Reader -> typed Slice`

### App

`pure contracts -> runtime executor -> thin Remote adapter -> application coordinator -> capability Provider -> UI state`

- UI/Provider/Repository 不传 operationId、path、surfaceId、routeId 或 actor 字符串；这些由 `OperationInvocationContext` 和 metadata 生成链注入。
- Remote adapter 不维护 URL、headers、decoder、retry 或 error 的第二套规则。
- production composition 只引用 Remote；Mock/fixture/alpha override 只存在于独立 mock package 和 alpha runner。

## 安全与可靠性

- required operation 缺失或非法 credential 返回结构化 401；actor/scope/role 不满足返回 403；对象防枚举可返回 404。
- 服务端先清除客户端 identity headers，再验证 JWT/device ticket 的 issuer、audience、exp、nbf/iat、scope 与 token version，并重建唯一 ActorContext。
- route guard 之后仍由 application 校验 owner/member/participant/admin；客户端 guard 不是安全边界。
- command 仅在 metadata 声明幂等且具有 key 时允许重试；deadline 使用剩余预算并向 HTTP、数据库、对象存储和消息执行传播；取消后不得继续产生副作用。
- 错误链固定为 metadata error -> Service RuntimeErrorResponse -> App CloudException/RuntimeFailure -> UI recovery -> telemetry/alert。

## 测试与准出

- `local_contract`：对象边界、生成合同、依赖方向、alpha/Remote 行为同构、default-deny 与反设计门禁。
- `api_integration`：Dart generated adapter 经 Gateway/直连服务访问真实存储，验证认证、BOLA、幂等、outbox、deadline/cancel 和结构化错误。
- `user_acceptance`：十条真实 Remote Scenario 在 gamma-local/设备上执行，不接受路径存在、动态 skip、自 seed 或 Memory adapter 作为主证据。
- 商业准出要求同一 commit 与 Graph hash 的 production AOT/SBOM、Web/OHOS 能力门、实时 SLO、灰度和故障注入回滚证据。

