# L3 Story：欢迎入口路由 (`welcome-entry-routing`)

> 所属能力：[`onboarding-and-identity-entry`](../spec.md)

> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为管理身份、Persona 或关系的用户，
我希望欢迎页、首页底栏、/create、/chat、/profile 相关登录门统一复用 safeLoginDismissFallback 与 AuthGateReason 契约，
从而安全地维持身份、画像与关系状态。

## 2. 范围与非目标

### In Scope

- “欢迎入口路由”的输入、可观察主路径、失败语义以及与父能力的交接。
- welcome_screen.dart 的首次打开、手动退出、会话过期三种提示语义。
- auth_gate.dart / app_router.dart / main_app_shell.dart 的强入口守卫与安全回退。
- 游客关闭登录、登录成功 redirect、AuthContinuation 自动续接。
- 微信 / Apple 第三方登录 SDK 接入细节。
- 账号注销、恢复申诉、数据导出等设置域生命周期动作。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 欢迎入口路由

- “欢迎入口路由”必须通过父能力公开契约交付可观察结果；失败时返回 canonical failure，不写入成功事实。

<a id="req-002"></a>
### REQ-002 服务本地契约引用边界

- 跨边界字段、operation 与错误语义只引用所属服务 contracts；本节点不得复制 wire 定义。

<a id="req-003"></a>
### REQ-003 强入口登录门关闭回安全态、成功到目标态

- 欢迎页、首页底栏、/create、/chat、/profile 相关登录门统一复用 safeLoginDismissFallback 与 AuthGateReason 契约。
- `/login` 根步骤关闭遵守宿主 dismiss policy；手机号、OTP、授权与绑定等内部步骤优先返回上一登录步骤，Android 系统返回与顶部返回保持同一状态迁移。
- 清理 pending continuation 只发生在根步骤最终关闭；内部返回不得误清理，成功后由原目标表面消费 continuation。

## 4. 契约引用

- canonical：`quwoquan_app/lib/runtime/auth/auth_gate.dart`
- canonical：`quwoquan_app/lib/runtime/auth/auth_continuation.dart`
- canonical：`quwoquan_app/lib/runtime/di/navigation/app_router.dart`
- canonical：`quwoquan_app/lib/runtime/shell/main_app_shell.dart`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 欢迎入口路由

- GIVEN 管理身份、Persona 或关系的用户具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“欢迎入口路由”对应的公开行为。
- THEN 通过父能力公开契约交付“欢迎入口路由”的可观察结果。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

<a id="gwt-002"></a>
### GWT-002 强入口登录门关闭回安全态、成功到目标态

- GIVEN 游客从欢迎页、底栏、/create、/chat 或 /profile 触发强登录入口。
- WHEN 用户关闭登录页或成功完成登录。
- THEN 关闭后返回不再触发登录门的安全状态，成功后经 AuthContinuation 进入原目标态。

## 6. 依赖

- 前置要求：[`onboarding-and-identity-entry`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 欢迎入口路由 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺少能够证明“欢迎入口路由”已满足当前规格的真实测试证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-002"></a>
### OPEN-002 强入口登录门关闭回安全态、成功到目标态

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：欢迎页、首页底栏、/create、/chat、/profile 相关登录门统一复用 safeLoginDismissFallback 与 AuthGateReason 契约。
- 完成判定：`GWT-002` 对应行为满足且真实测试 `spec_ref` 有效。
