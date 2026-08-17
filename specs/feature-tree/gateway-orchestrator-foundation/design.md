# L1 Design：网关编排基础 (`gateway-orchestrator-foundation`)

> 对应规格：[L1 spec](./spec.md)

## 1. 背景与设计目标

- 设计目标：提供网关统一入口、鉴权限流、防护策略与跨服务编排基础能力。

## 2. 领域模型与所有权

- authoritative ownership：拥有统一入口的请求上下文、边缘认证授权结果、限流决定、聚合执行状态和实时连接投递状态；不拥有下游业务事实。
- write boundary：只能通过本领域公开 command 修改其拥有事实。
- 非本域对象：不拥有其他 L1 的事实；跨域协作必须使用对方公开 command、query、projection 或 event。
- 非本域对象：不复制 metadata 中的字段、path、错误码和 wire 语义。

## 3. 上下文边界与协作

- 上下游只通过公开 command、query、projection 或 event 交换事实。

## 4. 架构与数据流

- 公开 TLS 入口只终止传输安全、服务静态资源并提供可信代理源 IP；业务 HTTP 统一进入 `api-edge`，按“验签并重建可信 actor -> minimum App Build -> generated ContractGraph operation 或 persisted query 授权 -> 共享 admission -> stable/candidate 裁决 -> 业务 owner”单轨执行。
- 限流状态以 `(environment, trusted subject, canonical operation)` 派生的不可逆摘要 key 存入共享 Redis；副本和 `prod` stable/candidate 不形成独立配额，rollout stage 不参与 key。
- 共享状态故障只执行 operation policy 声明的 fail-open/fail-closed，不得切换到进程内计数器；拒绝响应的 `Retry-After` 与 canonical recovery 秒数来自同一原子决定。
- App 入站设备、地域与运营商 header 在验签前删除；可信 device actor 只从已验签 token 的 `did` principal 重建，地域与运营商只由可信代理源 IP 和已固定摘要的 GeoIP/ASN 数据派生。Caddy 与业务 owner 均不持有第二套路由规则。
- REST command 继续进入生成的写 owner；GraphQL 仅承载登记的只读 Query Slice，版本/更新/恢复 REST 保持在 minimum gate 之外。
- [`orchestration-degradation-rollback`](./orchestration-degradation-rollback/spec.md)：在聚合调用、下游超时或路由变更失败时维持稳定响应契约，并通过显式降级和可审计回滚恢复服务
- [`realtime-gateway`](./realtime-gateway/spec.md)：提供有状态的双向实时会话、重连与投递确认
- [`request-context-propagation`](./request-context-propagation/spec.md)：让同一请求的主体、客户端、requestId、traceId 与 causationId 在同步和异步边界保持一致且可审计
- [`unified-entry-security`](./unified-entry-security/spec.md)：在统一入口完成认证、operation scope 授权、限流与安全观测，失败时拒绝进入业务 owner
- 工程边界由 spec 的“工程归属”声明；设计不复制具体实现文件。

## 5. 关键决策

<a id="dec-001"></a>
### DEC-001 统一入口先执行安全与上下文链，再路由到业务 owner
- 决策：统一入口先执行安全与上下文链，再路由到业务 owner。
- 理由：提供网关统一入口、鉴权限流、防护策略与跨服务编排基础能力。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 约束与影响：TLS/静态入口不得复制业务 path/operation/限流表；业务 owner 不接受绕过 `api-edge` 的公网入口，内部服务仍执行自身 generated authorization 作为 owner 边界。
- 关联要求：`REQ-001`
- 关联能力：[`orchestration-degradation-rollback`](./orchestration-degradation-rollback/spec.md)、[`realtime-gateway`](./realtime-gateway/spec.md)、[`request-context-propagation`](./request-context-propagation/spec.md)、[`unified-entry-security`](./unified-entry-security/spec.md)

<a id="dec-002"></a>
### DEC-002 商用治理态只在对外边界 fail-closed，进程内 guard 只强制 deadline 与身份授权
- 决策：operation 商用状态未达 ready 时的拒绝只在对外边界强制；业务服务进程内的入口 guard 只强制请求 deadline、身份验签与 operation 授权，不读取商用治理态。
- 理由：对外边界已对全部生成的 operation 描述符施加该门，生产流量必然先经过边界，进程内重复施加对真实流量的收益为零。
- 理由：进程内一并施加会掐死直连服务的取证路径，让未达 ready 的 operation 永远拿不到转 ready 所需的运行证据，形成自锁。
- 被否决方案：在进程内 guard 复制商用状态判定、按环境放宽该判定、或为取证单独开一条绕过 guard 的旁路。
- 约束与影响：商用治理态是准出与发布决策的输入，不是进程内访问控制的输入。
- 约束与影响：取证调用仍必须完整通过身份、授权与 deadline 三项强制，不因免除治理态判定而降低安全边界。
- 关联要求：`REQ-002`
- 关联能力：[`unified-entry-security`](./unified-entry-security/spec.md)、[`orchestration-degradation-rollback`](./orchestration-degradation-rollback/spec.md)

<a id="dec-003"></a>
### DEC-003 可信 device actor 由安装 ID 绑定会话并随 access token 签发
- 决策：端侧生成可重置的安装级 UUID；登录、匿名 bootstrap 与 refresh session 将其绑定到会话，服务端沿用冻结字节算法派生不可逆 `deviceActorId` 并写入 access token 的可选签名 `did` claim。access principal 可同时具有 account、persona 与 device actor，API Edge 删除所有入站裸身份 header 后仅从验签 principal 重建。
- 理由：灰度在登录前后和账号切换时必须保持同一安装 cohort，同时不能信任 App 可伪造的设备 header，也不能使用 IMEI、Android ID 或 IDFA 等不可重置硬件标识。
- 被否决方案：账号 ID 分桶、请求级随机、把裸 `X-Client-Device-Actor-Id` 当可信事实、为分桶额外建立兼容握手，以及更换既有派生算法导致全量重新洗牌。
- 约束与影响：老 token 没有 `did` 时只进入 stable 并计入 `missing_rollout_subject`；进入 5% 前必须证明旧 token 已自然过期或刷新且缺失率达门。安装 ID 重置产生新 actor 是预期隐私边界，旧 actor 不可恢复。
- 关联要求：`REQ-003`
- 关联能力：[`request-context-propagation`](./request-context-propagation/spec.md)、[`unified-entry-security`](./unified-entry-security/spec.md)

<a id="dec-004"></a>
### DEC-004 Rollout evaluator 使用分平台 HMAC 分桶和持久 candidate assignment
- 决策：每个 campaign 冻结 `campaignId`、candidate digest、`allocationKeyId` 和 `subjectKind=device_actor`。分桶 material 由 campaign、candidate、platform、device actor 以 NUL 分隔组成，取 `HMAC-SHA256` 前 8 字节无符号整数对 10000 取模；5%、20%、50%、100% 阈值分别为 500、2000、5000、10000。
- 决策：candidate 结果为“已有 assignment、内部白名单或 audience 命中且 bucket 小于阈值”的并集；命中后使用 subject HMAC digest 以原子 set-if-absent 持久化，保留至 campaign 结束后 30 天。阈值和 audience 只能扩大，只有 campaign rollback 可使所有 candidate 返回 stable。
- 理由：platform 进入 material 可使 Android、iOS、Web 分别获得同等比例样本，持久 assignment 可让地域/运营商定向用户在旅行或换网后不漂移，候选集合包含关系可直接被配置门禁证明。
- 被否决方案：总体请求流量抽样、按单实例粘滞、App 自报地域/运营商、Redis 丢失后静默重新分桶、修改 campaign salt 延续同一发布，以及把 5% 固定命名为某个地域或运营商阶段。
- 约束与影响：assignment Redis 必须启用复制和持久化，不可用或数据丢失是 critical rollout failure。
- 约束与影响：WebSocket/SSE 建连后固定服务池，stable/candidate 共享 admission 和业务事实。API Edge 自身先用内部单实例 canary 验证再滚动升级。
- 关联要求：`REQ-004`
- 关联能力：[`orchestration-degradation-rollback`](./orchestration-degradation-rollback/spec.md)

<a id="dec-005"></a>
### DEC-005 App/public 读面使用受控 GraphQL Query Slice，owner 读取保持 typed 边界，写面保持 REST command
- 决策：`POST /graphql` schema-first 且只有 Query。Query root 由公开 read operation/Query Slice 生成；有用户查询价值和授权边界的 projection、aggregate slice、external reference 可以暴露，append-only fact 只能经受控视图暴露，process manager/runtime session 只有确有用户可见读取时才暴露，没有 App read operation 的对象不进入 schema。
- 决策：Prod 仅执行发布包内签名 registry 已登记的 persisted query hash，不接受 query text、APQ miss 在线注册或 Mutation。每个 hash 精确绑定 canonical operation、对象集合、授权与签名成本计划。常规 depth 与顶层字段均不超过 3，4～5 必须分别绑定受审计例外引用，超过 5 一律拒绝。generator 按 queryClass 使用 detail 100、collection 300、page_composite 500 的常规 worst-case complexity 上限。超出本类上限必须绑定受审计例外引用，501～1000 在 runtime 仍强制要求引用，超过 1000 一律拒绝。variables 仍以 64 KiB、分页以 100 为硬上限。
- 决策：签名成本计划使用固定 `costModelVersion`，以 canonical JSON 的 SHA-256 摘要绑定基础复杂度、由变量路径驱动的列表倍数、owner call、batch key 与响应字节上限，并绑定对应 SLO。registry 加载时重算计划摘要与 worst-case；请求期在授权和执行前按实际 variables 重算复杂度，非整数或超过声明最大值的倍数变量直接拒绝。executor 必须返回强类型执行用量，API Edge 在响应前核对 owner call、batch key、响应字节以及实际编码字节数，缺失、漂移或超预算均 fail-closed。
- 决策：App 与公众业务读面进入 persisted GraphQL read plane。API Edge 聚合只暴露页面或外部门面 Query Slice。跨服务 owner 读取不绕行 App GraphQL，而是经 canonical Reader/Slice 的 typed application port 或受限内部 HTTP。后者必须在 owner 执行前验证 service principal、scope、internal visibility 与 ContractGraph operation identity。运营控制面使用 scoped operator/admin typed query，与 App/public 读面分开。
- 理由：Query Slice 可以统一查询入口而不泄露领域内部对象或强迫所有聚合根暴露；REST command 保留清晰的写 owner、幂等和恢复语义，也保证更新/恢复端点在 GraphQL 不可用或客户端低于 minimum 时仍可访问。
- 被否决方案：六类对象机械暴露、GraphQL Mutation、把所有 owner/control-plane 读取强制绕行 App GraphQL、未验签或未声明 scope 的内部 REST query、按 URL 猜测非业务例外、resolver 逐字段跨服务调用、在线登记未知 query、同一 App Build 长期 REST/GraphQL 双读择优，以及用领域模型版本参与请求路由。
- 约束与影响：首版嵌套读取只使用父 Slice 或批量 DataLoader。禁止用 resolver 逐字段远程调用规避 `maxOwnerCalls/maxBatchKeys`。成本例外只能扩大签名 registry 中的静态上限，不能绕过 variables、分页、执行用量或响应字节的请求期重验。旧 REST read 只有在最后消费 App 已低于 minimum 且观察期使用量为零后删除。source-only 校验只对结构违规 strict-zero，并以 PR 事件的 immutable base/candidate SHA 对 legacy REST identity 集合执行只减不增；全量 zero 仍是需要 hosted readiness、minimum-build 与零调用证据的 release cutover 门，不得用固定数量、allowlist 或 warn-only 替代。新 App 发布前必须对当前 stable 云通过真实 api_integration，candidate 云必须保留所有受支持 App 的 persisted query 与 REST command。
- 关联要求：`REQ-005`
- 关联能力：[`unified-entry-security`](./unified-entry-security/spec.md)、[`request-context-propagation`](./request-context-propagation/spec.md)

## 6. 质量与运行约束

- 沿用 AppRoot 全局质量约束并保持 metadata/code/test 单轨。
- GraphQL、REST command、minimum Build 和 rollout 裁决必须使用同一 generated ContractGraph operation 身份与 canonical error/recovery 语义；内部对象模型 `major.minor` 只参与不可变 Prod-full 基线 diff 和发布门禁，不形成运行期协商面。
- 观测必须区分 stable/candidate、platform、App Version/Build、region、carrier、operation、GraphQL reject、426 与 missing rollout subject，并分别报告去重安装、去重账号和请求比例；身份、IP 和 subject digest 不进入低基数指标标签。

## 7. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：按 canonical recovery action 重试、刷新或回滚到上一份已验证配置。
- 禁止 fallback：不得使用 Mock、旧 wire、双读双写或跨域直写伪造成功。
