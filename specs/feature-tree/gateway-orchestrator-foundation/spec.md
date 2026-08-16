# L1 Domain Service：网关编排基础 (`gateway-orchestrator-foundation`)

> 一句话定位：提供网关统一入口、鉴权限流、防护策略与跨服务编排基础能力。

## 1. 目标与用户价值

提供网关统一入口、鉴权限流、防护策略与跨服务编排基础能力。

## 2. 领域边界

### 本领域拥有

- 拥有统一入口的请求上下文、边缘认证授权结果、限流决定、聚合执行状态和实时连接投递状态；不拥有下游业务事实。
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

- 当前 AppRoot Scenario 不直接经过本领域；本领域只提供被业务领域调用的横切能力。

## 4. 业务能力

- [`orchestration-degradation-rollback`](./orchestration-degradation-rollback/spec.md)：在聚合调用、下游超时或路由变更失败时维持稳定响应契约，并通过显式降级和可审计回滚恢复服务
- [`realtime-gateway`](./realtime-gateway/spec.md)：提供有状态的双向实时会话、重连与投递确认
- [`request-context-propagation`](./request-context-propagation/spec.md)：让同一请求的主体、客户端、requestId、traceId 与 causationId 在同步和异步边界保持一致且可审计
- [`unified-entry-security`](./unified-entry-security/spec.md)：在统一入口完成认证、operation scope 授权、限流与安全观测，失败时拒绝进入业务 owner

## 5. 领域要求

<a id="req-001"></a>
### REQ-001 gateway orchestrator foundation 领域边界验收

- 领域边界、上下游依赖、工程映射和服务治理清晰。

<a id="req-002"></a>
### REQ-002 提供网关统一入口、鉴权限流、防护策略与跨服务编排基础能力

- 提供网关统一入口、鉴权限流、防护策略与跨服务编排基础能力。
- 网关为端侧唯一入口，业务服务不得直连暴露。
- 编排输出结构必须稳定；禁止兼容握手、请求期领域模型声明、多版本 wire 信封、字段双键读取和长期 shim。minimum 仍支持的历史 App 所使用 operation 是当前正式契约，须保留到支持窗口关闭。
- request/trace/page/session/user/device 字段必须全链路透传。

<a id="req-003"></a>
### REQ-003 可信安装身份与最低 App Build 门禁

- Android、iOS、Web 首次安装或首次打开站点生成可重置 UUID v4 install ID；重启、登录、退出和账号切换保持，卸载重装、清除 App 数据或浏览器站点数据后重新生成，不读取硬件或广告标识。
- 登录、匿名 bootstrap 和 refresh session 均绑定 install ID；服务端使用冻结算法派生不可逆 `deviceActorId`，access token 以可选签名 `did` claim 同时承载 account、persona 和 device actor。网关必须先删除入站裸设备身份 header，验签后再从 principal 重建可信上下文。
- 老 access token 缺少 `did` 时请求固定进入 stable 并计入 missing subject，不得使用请求级随机 fallback；`deviceActorId` 只用于分桶、去重及已声明的设备 actor 行为，不作为认证凭证或授权条件。
- API Edge 对低于平台 minimum supported Build 的普通业务请求返回 HTTP 426 和 canonical `client_upgrade_required`；版本查询、更新下载、恢复页、官网和完成更新所必需的认证入口不受阻断。

<a id="req-004"></a>
### REQ-004 API Edge 拥有生产灰度裁决

- 公网入口只处理 TLS、静态资源与可信代理链；必须删除入站设备、地域和运营商声明，业务 stable/candidate 路由只由 API Edge 基于可信 principal、平台 Build 和可信源 IP 派生属性裁决。
- 请求顺序固定为 credential verification、minimum Build gate、operation/persisted query authorization、共享 admission、rollout decision、owner proxy；stable/candidate 使用同一 admission scene 和共享业务存储，stage 不得进入限流 key。
- Android、iOS、Web 按可信安装实例分平台确定性分桶；同一 campaign 的 candidate assignment 单调保持，地域、运营商或网络变化不使已入组实例回到 stable。
- WebSocket/SSE 只在建连时确定服务池，连接生命周期内不切换。普通请求只粘滞服务池，不粘滞单实例。
- assignment store 故障/丢失、candidate identity 漂移或非法缩小 cohort 时必须使 campaign 自动 rollback；不得让 Caddy、业务 owner 或进程内 fallback 复制灰度判断。

<a id="req-005"></a>
### REQ-005 App/public GraphQL 读面、typed owner 读取与 REST command 写入分离

- App 与公众业务读面的统一入口为 `POST /graphql`；Query root 只按有用户查询价值、授权边界和成本预算的 Query Slice 暴露，不按聚合根或对象类别机械开放，且不提供 GraphQL Mutation。
- Prod 只接受随受审计发布包签名并登记的 persisted query hash；hash 必须精确绑定 operation、对象集合、授权和成本预算，未知 hash、任意 query text、在线注册、超成本查询和 mutation 全部拒绝。
- `POST /graphql` 的 canonical operation 只能在签名 registry 解出 persisted query hash 后由 GraphQL 专属 authorizer 裁决；通用 REST method/path guard 不得把共享 `/graphql` 路径误判为重复路由，也不得代替 registry 猜测具体 operation。普通 REST route 仍须保持 method/path 唯一并在冲突时 fail-closed。
- GraphQL 专属 authorizer 的部署描述符集合必须包含 gateway-owned persisted query operation；它不因 gateway 缺少 REST owner upstream 而从 ContractGraph 授权集合消失，同时不得把 gateway operation 注入通用 REST owner proxy。
- App 侧 gateway-owned persisted query 必须由 `lib/service/api_edge/<context>/<object>/{application,adapters}` 承载对象级 typed port 与 Remote adapter；业务对象只消费该 public port，不得直接持有签名 hash、GraphQL envelope、generated transport 或 invocation context 装配。
- 嵌套字段只能读取父 Query Slice 或使用批量 DataLoader，不得由 resolver 逐字段跨服务远程调用；所有状态变更继续进入 canonical REST command/write owner。
- 跨服务业务读取使用对象 owner 的 typed query，可经进程内 application port 或受限内部 HTTP 传输，不绕行 App GraphQL。内部 HTTP 必须绑定 canonical operation/Reader/Slice、验签 service principal、最小 scope、`internal` visibility 与 ContractGraph operation identity，且不进入 App/public exposure。
- 运营控制面读取可保留明确的 typed REST query，但必须使用验签 operator/admin principal、显式 scope 与 canonical operation，不得作为 App 或公众业务读面。非业务 HTTP 入口另行声明闭集 `transport_role`，且不得返回普通业务 Query Slice。路径名称不产生隐式豁免。
- 历史 App 的 REST read 在其 Build 仍受支持期间是正式契约；迁移必须按对象执行“新增 persisted query、新 App 切换、验证、minimum 提升、删除旧 REST read”，同一 App Build 不得长期双读或择优返回。
- 领域模型 `major.minor`、ContractGraph digest 只用于 build/deploy/release evidence 与变更门禁，不进入请求、路由、GraphQL response 或 App UI；端云组合仅由受支持 operation、当前 stable 集成验证和 minimum Build 治理。

## 6. 领域验收

<a id="dom-001"></a>
### DOM-001 gateway orchestrator foundation 领域边界验收

- 条件：本领域收到有效输入且前置领域事实成立。
- 可观察结果：领域边界、上下游依赖、工程映射和服务治理清晰。
- 禁止结果：不得绕过本领域公开 command/query/event 写入其拥有事实。
- 可观察结果：历史支持 App 对 candidate 云、新 App 对当前 stable 云、以及同版本端云三种组合均通过对应 persisted query/REST command 证据；不存在握手或请求期模型协商。

## 7. 工程归属

- App：`quwoquan_app/lib/service/api_edge`、`quwoquan_app/lib/service/realtime_gateway`
- Metadata（协作引用，不用于代码归属）：`quwoquan_service/contracts/metadata/_shared`
- Service：`quwoquan_service/runtime`、`quwoquan_service/services/api-edge`、`quwoquan_service/services/realtime-gateway`
- 测试：
  - `local_contract`：`quwoquan_service/runtime`
  - `api_integration`：`quwoquan_service/runtime`
  - `user_acceptance`：`quwoquan_ops/tests/acceptance/user_acceptance`

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 gateway orchestrator foundation 领域边界验收

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：领域边界、上下游依赖、工程映射和服务治理清晰。
- 完成判定：`DOM-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 GraphQL hosted read plane 商用证据未完成，阻断全部 legacy REST query 迁移

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚缺 `POST /graphql` 统一读入口的 hosted 商用证据（api-edge contract 以 `gap_id: GATEWAY_GRAPHQL_READ_HOSTED_EVIDENCE` 声明 `commercial.status: blocked`）。
  - 缺 API Edge composition root 接入、签名 persisted query registry 发布包与真实 owner Query Slice 的 api_integration 证据。
  - 在该前置解除前，`verify_graphql_read_rest_command_single_track.py` 计数的 App/public legacy REST query（当前 167 条）无一可完成商用切轨；`content.post.GetPost` 五 slice persisted 链虽已双侧合约齐备，App 仍必须走 REST。
  - 例外：SearchPage 专属路由已 `commercial: ready`，是当前唯一 hosted GraphQL 读面先例。
- 完成判定：[`DOM-001`](#dom-001) 对应行为在 hosted GraphQL 读面上满足并有真实测试 `spec_ref`，具体为下列全部达成。
  - api-edge `/graphql` 路由 `commercial.status` 转为 `ready` 且 gap_id 撤销。
  - composition root 装配、签名 registry 发布与至少一条 owner Query Slice（建议 `content.post.GetPost`）的 api_integration 证据绑定本节点。
  - 随后首批迁移波次（零 App 消费的 `GetCounters`、`GetHelperRead`、`GetOwnedMediaAsset` 优先裁决，`GetPost` 作为首条真实切轨）使 `appPublicLegacyRestQueryRoutes` 从 167 严格下降。
