# L3 Story：认证 Token 生命周期 (`auth-token-lifecycle`)

> 所属能力：[`auth-profile-snapshot`](../spec.md)

> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)

> 设计归属：[L1 DEC-001](../../design.md#dec-001)

## 1. 用户价值

作为管理身份、Persona 或关系的用户，
我希望服务端 contract、App session store 与错误码语义一致，不再存在“token 已失效但客户端仍保留 authenticated”的灰区，
从而安全地维持身份、画像与关系状态。

## 2. 范围与非目标

### In Scope

- “认证 Token 生命周期”的输入、可观察主路径、失败语义以及与父能力的交接。
- RefreshToken 返回新 accessToken/new refreshToken 并轮换持久化。
- Logout 吊销 refresh token，旧 refreshToken 不可再次刷新。
- sessionExpired prompt 与 manualLoggedOut prompt 区分。
- 微信 / Apple 票据登录与 passkey challenge/assertion 的客户端 contract 预留。
- CloudHttpClient 统一 refresh once -> retry 自动化链路。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 认证 Token 生命周期

- “认证 Token 生命周期”必须通过父能力公开契约交付可观察结果；失败时返回 canonical failure，不写入成功事实。

<a id="req-002"></a>
### REQ-002 服务本地契约引用边界

- 跨边界字段、operation 与错误语义只引用所属服务 contracts；本节点不得复制 wire 定义。

<a id="req-003"></a>
### REQ-003 refresh token 轮换成功，logout 后旧 token 不可复用

- 服务端 contract、App session store 与错误码语义一致，不再存在“token 已失效但客户端仍保留 authenticated”的灰区。
- 微信 / Apple 与 passkey 相关 repository 方法、page id、path、错误码与 metadata 同源；未开通的客户端能力不引入第二真相源。

## 4. 契约引用

- canonical：`quwoquan_service/services/user-service/contracts/account/user_account/operations.yaml`
- canonical：`quwoquan_service/services/user-service/contracts/account/user_account/errors.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 认证 Token 生命周期

- GIVEN 管理身份、Persona 或关系的用户具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“认证 Token 生命周期”对应的公开行为。
- THEN 通过父能力公开契约交付“认证 Token 生命周期”的可观察结果。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

<a id="gwt-002"></a>
### GWT-002 refresh token 轮换成功，logout 后旧 token 不可复用

- GIVEN 已认证用户持有有效 refresh token。
- WHEN 用户刷新会话或登出后重放旧 token。
- THEN 刷新返回轮换后的会话，登出后的旧 token 被一致拒绝且端侧不保留伪 authenticated 状态。

## 6. 依赖

- 前置要求：[`auth-profile-snapshot`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L1 DEC-001](../../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 认证 Token 生命周期 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺少能够证明“认证 Token 生命周期”已满足当前规格的真实测试证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。
