# L2 Business Capability：运行流式策略 (`run-stream-policy`)

> 所属领域：[`assistant-run-learning`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

规范助手 Run/Stream 主链路的协议、策略模板与域路由行为。

## 2. 范围与非目标

### In Scope

- 由本目录 Story 组合交付“run-stream-policy”的独立业务结果。

### Out of Scope

- 其他 L2 的事实所有权、metadata schema 与实现施工步骤。

## 3. Journey / Scenario 贡献

- [`JNY-009 / SCN-017`](../../spec.md#scn-017)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：规范助手 Run/Stream 主链路的协议、策略模板与域路由行为，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。

## 4. Story



- [`policy-template-routing`](./policy-template-routing/spec.md)：定义“策略模板路由”的可观察主路径、失败语义及父能力交接。
- [`run-stream-protocol`](./run-stream-protocol/spec.md)：`run_started` 后必须先以 `process_replace` 建立过程快照；每个 `seq` 对同一 run。
- [`run-sync-contract`](./run-sync-contract/spec.md)：定义“运行同步契约”的可观察主路径、失败语义及父能力交接。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 run stream policy 能力 SIT

- 本能力必须组合直属 Story 与公开契约，交付“规范助手 Run/Stream 主链路的协议、策略模板与域路由行为”所定义的业务结果；失败终态必须可区分且不得伪造成功。

<a id="req-002"></a>
### REQ-002 Run/Stream 的输入输出字段必须与端侧协议一致，禁止服务端私有字段外泄

- Run/Stream 的输入输出字段必须与端侧协议一致，禁止服务端私有字段外泄。
- 策略模板与域路由必须版本化，可灰度、可回滚。

## 6. 契约与依赖

- 上游能力：[`assistant-run-learning`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 run stream policy 能力 SIT

- GIVEN 执行“run stream policy 能力”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“run stream policy 能力”对应动作。
- THEN 直属 Story 共同交付“规范助手 Run/Stream 主链路的协议、策略模板与域路由行为”，失败终态可区分且不产生伪成功事实。
