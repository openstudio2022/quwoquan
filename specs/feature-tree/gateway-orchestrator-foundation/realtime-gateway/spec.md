# L2 Business Capability：实时通信网关 (`realtime-gateway`)

> 所属领域：[`gateway-orchestrator-foundation`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

提供有状态的双向实时会话、重连与投递确认

## 2. 范围与非目标

### In Scope

- 由本目录 Story 组合交付“realtime-gateway — 统一实时通信网关”的独立业务结果。

### Out of Scope

- 其他 L2 的事实所有权、metadata schema 与实现施工步骤。

## 3. Journey / Scenario 贡献

- [`JNY-007 / SCN-016`](../../spec.md#scn-016)
  - 本能力接收：该 Scenario 进入本能力边界的已授权主体与 canonical 输入。
  - 本能力处理：提供有状态的双向实时会话、重连与投递确认。
  - 本能力输出：直属 Story 组合产生的可观察结果与明确失败终态。
  - 失败时终态：保留已确认事实，并返回可恢复的 canonical failure。

## 4. Story



- [`realtime-channel-delivery`](./realtime-channel-delivery/spec.md)：连接状态必须由 Redis 支撑多节点查询；网关只消费 owner 事件，不直接写业务 MongoDB。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 realtime gateway 能力 SIT

- 本能力必须组合直属 Story 与公开契约，交付“提供有状态的双向实时会话、重连与投递确认”所定义的业务结果；失败终态必须可区分且不得伪造成功。

<a id="req-002"></a>
### REQ-002 必须使用 `runtime/config`、`runtime/observability`、`runtime/http`（健康检查端点）

- 必须使用 `runtime/config`、`runtime/observability`、`runtime/http`（健康检查端点）
- 禁止在 realtime-gateway 中直接操作 MongoDB（只消费事件，不读写业务数据）
- WebSocket 帧格式必须全局统一（所有 topic 共用）
- 外部渠道 Adapter 必须实现 `ChannelAdapter` SPI interface
- 连接状态必须存储在 Redis（支持多节点查询在线状态）
- realtime-gateway 必须独立部署，禁止与 chat-service 混部

## 6. 契约与依赖

- 上游能力：[`gateway-orchestrator-foundation`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 realtime gateway 能力 SIT

- GIVEN 执行“realtime gateway 能力”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“realtime gateway 能力”对应动作。
- THEN 直属 Story 共同交付“提供有状态的双向实时会话、重连与投递确认”，失败终态可区分且不产生伪成功事实。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 realtime gateway 能力 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：提供有状态的双向实时会话、重连与投递确认。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效
