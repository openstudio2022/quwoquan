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
- 编排输出结构必须稳定；禁止协议版本分支与 wire 兼容窗口（只认当前契约形状）。
- request/trace/page/session/user/device 字段必须全链路透传。

## 6. 领域验收

<a id="dom-001"></a>
### DOM-001 gateway orchestrator foundation 领域边界验收

- 条件：本领域收到有效输入且前置领域事实成立。
- 可观察结果：领域边界、上下游依赖、工程映射和服务治理清晰。
- 禁止结果：不得绕过本领域公开 command/query/event 写入其拥有事实。

## 7. 工程归属

- App：`quwoquan_app/lib/cloud/runtime`、`quwoquan_app/lib/app`
- Metadata（协作引用，不用于代码归属）：`quwoquan_service/contracts/metadata/_shared`
- Service：`quwoquan_service/runtime`、`quwoquan_service/services/realtime-gateway`
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
