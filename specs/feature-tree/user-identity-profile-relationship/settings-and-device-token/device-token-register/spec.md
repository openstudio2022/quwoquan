# L3 Story：设备 Token 登记 (`device-token-register`)

> 所属能力：[`settings-and-device-token`](../spec.md)

> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为管理身份、Persona 或关系的用户，
我希望设备推送 Token 可幂等登记、替换和撤销，通知只投递到有效端点，
从而安全地维持身份、画像与关系状态。

## 2. 范围与非目标

### In Scope

- “设备 Token 登记”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 设备 Token 登记

- “设备 Token 登记”必须通过父能力公开契约交付可观察结果；失败时返回 canonical failure，不写入成功事实。

<a id="req-002"></a>
### REQ-002 服务本地契约引用边界

- 跨边界字段、operation 与错误语义只引用所属服务 contracts；本节点不得复制 wire 定义。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 设备 Token 登记

- GIVEN 管理身份、Persona 或关系的用户具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“设备 Token 登记”对应的公开行为。
- THEN 通过父能力公开契约交付“设备 Token 登记”的可观察结果。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`settings-and-device-token`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 设备令牌登记结果子句尚未逐条绑定

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：缺 `GWT-001` 两条结果子句的逐条证据，未区分登记主路径与失败语义分别由哪条断言证明。
- 完成判定：`GWT-001.t1` 与 `GWT-001.t2` 各自被真实测试 `spec_ref` 绑定。

<a id="open-002"></a>
### OPEN-002 FCM registration token 到 Firebase Installation ID 的契约迁移

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺 user-service 对 Firebase Installation ID、registration token、轮换与撤销关系的正式契约及端云验收证据；Android 当前固定 `firebase-messaging 25.0.2` 以维持既有 registration token 语义，不得把 Firebase Installation ID 静默写入旧 token 字段，否则设备替换、撤销、去重和投递回执会失去同一身份含义。
- 完成判定：先在 user-service 设备端点 contracts 明确 installation、registration token、轮换与撤销关系，再完成 metadata/codegen、App token 刷新、服务端幂等登记、通知投递与真机前台/后台/终止态验收；全部证据引用本 Story 后方可解除 Android 依赖固定。
