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

- 公开 TLS 入口只终止传输安全和服务静态资源；业务 HTTP 统一进入 `api-edge`，按“验签身份 -> generated ContractGraph operation 授权 -> 共享 admission -> 业务 owner”单轨执行。
- 限流状态以 `(environment, trusted subject, canonical operation)` 派生的不可逆摘要 key 存入共享 Redis；副本和 `prod` stable/gray 不形成独立配额，rollout stage 不参与 key。
- 共享状态故障只执行 operation policy 声明的 fail-open/fail-closed，不得切换到进程内计数器；拒绝响应的 `Retry-After` 与 canonical recovery 秒数来自同一原子决定。
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

## 6. 质量与运行约束

- 沿用 AppRoot 全局质量约束并保持 metadata/code/test 单轨。

## 7. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：按 canonical recovery action 重试、刷新或回滚到上一份已验证配置。
- 禁止 fallback：不得使用 Mock、旧 wire、双读双写或跨域直写伪造成功。
