# L3 Story：运行同步契约 (`run-sync-contract`)

> 所属能力：[`run-stream-policy`](../spec.md)

> Journey / Scenario：[`JNY-009 / SCN-017`](../../../spec.md#scn-017)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为使用小趣的用户或助手运营者，
我希望同步链路不得输出未声明字段；错误码必须可定位模块与原因，
从而获得可解释、可恢复且可持续改进的助手结果。

## 2. 范围与非目标

### In Scope

- “运行同步契约”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 运行同步契约

- “运行同步契约”必须通过父能力公开契约交付可观察结果；失败时返回 canonical failure，不写入成功事实。

<a id="req-002"></a>
### REQ-002 同步链路不得输出未声明字段；错误码必须可定位模块与原因

- 同步链路不得输出未声明字段；错误码必须可定位模块与原因。

<a id="req-003"></a>
### REQ-003 请求上下文字段（user/page/session/trace）必须完整透传

- 请求上下文字段（user/page/session/trace）必须完整透传。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 运行同步契约

- GIVEN 使用小趣的用户或助手运营者具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“运行同步契约”对应的公开行为。
- THEN authenticated actor 与 App 的 canonical `page/session/surface/route/operation/trace` headers 随 command 到达服务端；服务端只从可信 transport metadata 写入运行审计上下文，`traceId` 保持可关联。
- AND command body 伪造的 `requestContext` 被 canonical invalid_argument 拒绝，公开 response 不回显内部审计上下文或任何未声明字段。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`run-stream-policy`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

