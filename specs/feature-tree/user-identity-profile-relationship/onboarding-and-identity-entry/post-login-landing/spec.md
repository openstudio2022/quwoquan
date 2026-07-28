# L3 Story：内容登录落点 (`post-login-landing`)

> 所属能力：[`onboarding-and-identity-entry`](../spec.md)

> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为管理身份、Persona 或关系的用户，
我希望从欢迎页、评论、关注、消息、创作等登录入口完成登录后，不需要用户手动重复操作即可继续原目标态，
从而安全地维持身份、画像与关系状态。

## 2. 范围与非目标

### In Scope

- “内容登录落点”的输入、可观察主路径、失败语义以及与父能力的交接。
- applyLoginResult 后 accessToken/refreshToken/ownerId/activeSubAccountId 落盘与恢复。
- 登录成功返回 redirect 或执行 AuthContinuation。
- 游客关闭登录返回安全态，不触发受限动作残留。
- token 过期后的自动 refresh/retry 细节。
- 多设备最近登录记录与设备审计页。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 内容登录落点

- “内容登录落点”必须通过父能力公开契约交付可观察结果；失败时返回 canonical failure，不写入成功事实。

<a id="req-002"></a>
### REQ-002 服务本地契约引用边界

- 跨边界字段、operation 与错误语义只引用所属服务 contracts；本节点不得复制 wire 定义。

<a id="req-003"></a>
### REQ-003 登录成功后恢复 owner/subAccount 上下文并进入目标态

- 从欢迎页、评论、关注、消息、创作等登录入口完成登录后，不需要用户手动重复操作即可继续原目标态。
- 只有 `AuthSessionGrant` 可以进入 `applyLoginResult` 与消费 `AuthContinuation`；社交 `phoneBindingRequired`、授权完成或 OTP 单项完成均不是登录成功终态。

## 4. 契约引用

- canonical：`quwoquan_app/lib/core/auth/auth_session.dart`
- canonical：`quwoquan_app/lib/core/auth/auth_continuation.dart`
- canonical：`quwoquan_app/lib/ui/user/pages/login_page.dart`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 内容登录落点

- GIVEN 管理身份、Persona 或关系的用户具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“内容登录落点”对应的公开行为。
- THEN 通过父能力公开契约交付“内容登录落点”的可观察结果。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

<a id="gwt-002"></a>
### GWT-002 登录成功后恢复 owner/subAccount 上下文并进入目标态

- GIVEN 用户从欢迎页、评论、关注、消息或创作入口被要求登录。
- WHEN 登录成功并应用登录结果。
- THEN owner 与 activeSubAccount 上下文恢复，且 AuthContinuation 将用户带回原目标态而无需重复操作。
- AND 社交首登绑定手机号未完成时不写入 session、不进入目标态且 continuation 保持待续接。

## 6. 依赖

- 前置要求：[`onboarding-and-identity-entry`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 内容登录落点 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺少能够证明“内容登录落点”已满足当前规格的真实测试证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-002"></a>
### OPEN-002 登录成功后恢复 owner/subAccount 上下文并进入目标态

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：从欢迎页、评论、关注、消息、创作等登录入口完成登录后，不需要用户手动重复操作即可继续原目标态。
- 完成判定：`GWT-002` 对应行为满足且真实测试 `spec_ref` 有效。
