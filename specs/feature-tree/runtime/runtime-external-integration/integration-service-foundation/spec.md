# L3 Story：集成服务基础 (`integration-service-foundation`)

> 所属能力：[`runtime-external-integration`](../spec.md)

> Journey / Scenario：[`JNY-007 / SCN-016`](../../../spec.md#scn-016)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为开发、测试或运维角色，
我希望对外只暴露标准化接口，禁止端侧直接调用供应商 API，
从而让调用方获得稳定结果，并让维护者能够定位和恢复失败。

## 2. 范围与非目标

### In Scope

- “集成服务基础”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 集成服务基础

- 对外只暴露标准化接口，禁止端侧直接调用供应商 API。

<a id="req-002"></a>
### REQ-002 服务必须遵循 metadata-first 与 DDD 单向依赖

- 服务必须遵循 metadata-first 与 DDD 单向依赖。
- 对外只暴露标准化接口，禁止端侧直接调用供应商 API。

<a id="req-003"></a>
### REQ-003 错误码覆盖定位不可用、上游超时、服务不可用等场景

- 错误码覆盖定位不可用、上游超时、服务不可用等场景。
- LocationPoi 端侧解析元数据驱动，禁止硬编码字段名；与 content 域 DTO 模式一致，make verify-metadata + make codegen-app 通过。
- 云侧抛出异常时，code 与 user_message 统一定义于 errors.yaml，生成 Go 文件可直接使用（无硬编码）。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 集成服务基础

- GIVEN 开发、测试或运维角色具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“集成服务基础”对应的公开行为。
- THEN 对外只暴露标准化接口，禁止端侧直接调用供应商 API。
- AND 失败时返回 canonical failure，且不产生伪成功事实。
- AND 请求状态、provider attempt、dead letter 与指标快照必须读取同一 MongoDB 可靠任务事实；死信恢复以 `Idempotency-Key` 持久化唯一 command receipt，同键重放返回首次回执、同键换任务失败关闭。
- AND 本 Story 的 Alpha/Beta/Gamma Provider 只使用受管 sandbox/nonprod tenant，不替代第一方 HTTP/application/store；Prod 正式 Provider 商用证据仍由 `capability-provider-commercial-readiness-gate` 独立准出。

## 6. 依赖

- 前置要求：[`runtime-external-integration`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)
