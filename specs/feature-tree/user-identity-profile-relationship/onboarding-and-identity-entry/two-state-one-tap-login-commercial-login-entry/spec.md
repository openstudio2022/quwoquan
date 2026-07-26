# L3 Story：两态一键登录与手机号登录 (`two-state-one-tap-login-commercial-login-entry`)

> 所属能力：[`onboarding-and-identity-entry`](../spec.md)

> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为管理身份、Persona 或关系的用户，
我希望本机号码首次登录在服务端完成账号、persona、credential、device 与 consent 持久化，
从而安全地维持身份、画像与关系状态。

## 2. 范围与非目标

### In Scope

- “两态一键登录与手机号登录”的输入、可观察主路径、失败语义以及与父能力的交接。
- LoginPage 两状态同构高保布局与响应式截图。
- 本地历史账号摘要与服务端二次登录。
- 运营商 SDK capability/hint/login 链路。
- 手机号验证码登录全状态 UI 与异常逃生路径。
- ResolveOneTapLoginHint / LoginOneTap metadata 契约。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 两态一键登录与手机号登录

- 本机号码首次登录在服务端完成账号、persona、credential、device 与 consent 持久化。

<a id="req-002"></a>
### REQ-002 本机号码一键创建默认账号

- 本机号码首次登录在服务端完成账号、persona、credential、device 与 consent 持久化。
- App 只消费服务端返回的登录结果并写入 remembered summary。

<a id="req-003"></a>
### REQ-003 两状态高保同构与响应式

- returningAccount 与 carrierPhone 两状态共享同一 LoginFrame 信息架构。
- 移动、平板与 Web 宽屏下关键区域不重叠、不拉伸、不漂移。

<a id="req-004"></a>
### REQ-004 协议、错误与降级单通道且不悬空

- 协议、SDK 不可用、超时、账号受限和关闭路径均有明确恢复动作。
- 任一失败状态都不会绕过结构化错误语义或触发登录回环。

<a id="req-005"></a>
### REQ-005 无历史摘要且运营商不可用时进入手机号验证码登录

- 无历史摘要且运营商不可用时，用户在同一 LoginFrame 内可继续用手机号验证码登录。
- 关闭、其它登录方式和手机号输入错误态均不触发二次登录弹窗。

<a id="req-006"></a>
### REQ-006 手机号验证码 12 状态同构高保

- 手机号验证码 12 状态在同一布局骨架内完成，不发生控件错位。
- 验证码输入、粘贴、退格与错误恢复均有 widget 或 golden 证据。

<a id="req-007"></a>
### REQ-007 手机号验证码异常不拦截用户

- 每类 OTP 异常都有明确下一步，并保留用户可恢复路径。
- 修改手机号会清空验证码与错误，关闭和成功目标态不回环。

<a id="req-008"></a>
### REQ-008 手机号验证码登录创建或恢复账号

- 手机号验证码登录只走 LoginWithPhone metadata 契约。
- 创建账号必须原子写入账号、Persona、凭证、设备与同意事实；恢复登录不得重复创建这些对象。

<a id="req-009"></a>
### REQ-009 metadata/codegen/auth policy 与商用登录契约一致

- ResolveOneTapLoginHint 是 public operation。
- LoginOneTap request/response 字段由 metadata 生成并被 App RemoteRepository 消费。
- SendOtp / LoginWithPhone request/response 字段由 metadata 生成并被 App RemoteRepository 消费。
- SendOtp response 只可表达 maskedPhone、expiresInSeconds、deliveryStatus、requestId、challengeId、retryAfterSeconds，且不得包含验证码。
- USER.AUTH carrier/consent/account 状态错误码生成 Dart/Go 常量。
- USER.AUTH otp_mismatch/otp_expired 与频控错误可映射到手机号 OTP UI 状态。
- 旧未登记 /auth/login 与 credentialType/credentialKey 登录兼容口径不得回归。
- SendOtp / LoginWithPhone / LoginOneTap / ResolveOneTapLoginHint 在 metadata 同源声明 commercial、authorization、安全、隐私、可靠性、遥测、错误码与 SLO，App ContractGraph lock 通过正式 handoff 接受。

<a id="req-010"></a>
### REQ-010 手机号 OTP 服务商与错误语义契约

- SendOtp provider failure 返回结构化可恢复错误，App 映射 sendFailed。
- rate_limited 带 retryAfter 语义，App 进入倒计时。
- LoginWithPhone 缺 agreementVersion/privacyVersion 返回 consent_required。
- otp mismatch 保留验证码，otp expired 进入重新获取。
- 每个 USER.AUTH 错误码都有 recovery.action、disruptionLevel、双语文案与唯一 LoginErrorSurface。
- RuntimeErrorResponse 不向客户端返回 debugMessage、authCode、token、secret 或 provider 原始 URL。

<a id="req-011"></a>
### REQ-011 真机与灰度商用证据

- iPhone 17 截图覆盖图一/图二。
- iPhone 17 截图覆盖手机号验证码 12 状态。
- Android/iOS 运营商 SDK smoke 覆盖可用与不可用。
- Android/iOS 短信 provider smoke 覆盖发送成功、频控和失败。
- Web/iPad 截图覆盖居中 frame。
- 登录页曝光、状态解析、主按钮点击、成功、失败、关闭埋点可查。
- 灰度与回滚策略写入发布 runbook 或对应商用卡点。

<a id="req-012"></a>
### REQ-012 当历史会话与运营商能力都不可用，或用户主动选择“其它手机号”时，用户可以在同一骨架内用手机号验证码完成登录，不会被异常、频控或服务商失败卡死

- 当历史会话与运营商能力都不可用，或用户主动选择“其它手机号”时，用户可以在同一骨架内用手机号验证码完成登录，不会被异常、频控或服务商失败卡死。
- `LoginPage` 的统一登录骨架、手机号 OTP 全状态高保布局、深浅色、无障碍、响应式与截图验收。
- 登录页退出控件只由宿主导航语义决定，与错误状态无关：栈内入口使用返回箭头并 `popPrevious`
- 受限目标触发的强登录使用 `safeFallback` 关闭到公开安全态。
- Web/弹层宿主使用 `hostControlledClose`。错误组件不得注入 X、返回按钮或改写关闭策略。
- 登录原因只由 `AuthGateReason/AuthContinuation` 决定；返回账号、运营商和手机号状态切换不得覆盖来源标题与说明。
- 返回账号摘要必须同时满足“可识别且可执行”：定制昵称或真实脱敏标识至少存在一项，并且存在有效 refresh、可预填手机号或可执行的记住社交方式。系统默认昵称、头像或“上次使用的账号”等占位不得单独创建返回账号态。
- 昵称与头像解耦：`nicknameCustomized=true` 且 `displayName` 非空时展示真实昵称；系统默认昵称、旧数据缺字段或空昵称统一展示“欢迎回来”，端侧禁止按 `新同学_*` 格式猜测。
- 返回账号会话过期时主按钮统一为“短信验证码登录”；说明句保持“登录信息已过期，请用短信验证码重新登录”的完整语法。
- 趣我圈花瓣中心使用明确的两层花蕊；登录页、欢迎页、Android、iOS、Web maskable 图标与 favicon 必须由同一个 `WelcomeAppIconPainter` 生成并通过资产哈希校验，禁止平台图标各自维护。
- 验证码必须显示为 6 个独立方框；隐藏输入只能用于焦点、粘贴和键盘控制，普通输入框不得外露。
- 所有异常态必须就近提示，并保留关闭、修改手机号、重试或切换其它方式的清晰路径。手机号格式/验证码不匹配使用字段错误。
- 发送失败、限流、验证码过期使用表单内联错误。
- 社交失败只在其他登录方式区域展示。
- 同一次失败只允许一个可见反馈。

## 4. 契约引用

- canonical：`quwoquan_app/test/local_contract/ui/user/login_page_widget__local_contract_test.dart`
- canonical：`quwoquan_app/test/local_contract/core/auth/auth_session_store__local_contract_test.dart`
- canonical：`quwoquan_app/test/local_contract/cloud/user/account_identity_facets__contract__local_contract_test.dart`
- canonical：`quwoquan_service/services/user-service/contracts/account/user_account/operations.yaml`
- canonical：`quwoquan_service/services/user-service/tests/api_integration/account/user_account/auth_contract__api_integration_test.go`
- canonical：`quwoquan_app/test/local_contract/core/widgets/app_cached_network_image__local_contract_test.dart`
- canonical：`quwoquan_app/test/local_contract/ui/user/journeys/commercial_login_recovery_journey__local_contract_test.dart`
- canonical：`quwoquan_service/services/user-service/contracts/account/user_account/errors.yaml`
- canonical：`quwoquan_app/test/local_contract/core/auth/auth_gate_matrix_contract__local_contract_test.dart`
- canonical：`quwoquan_app/test/local_contract/ui/user/goldens`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 两态一键登录与手机号登录

- GIVEN 管理身份、Persona 或关系的用户具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“两态一键登录与手机号登录”对应的公开行为。
- THEN 本机号码首次登录在服务端完成账号、persona、credential、device 与 consent 持久化。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

<a id="gwt-011"></a>
### GWT-011 真机与灰度商用证据

- GIVEN Android、iOS、Web 与 iPad 的商用登录包处于受控灰度。
- WHEN 用户完成一键、短信或失败恢复路径。
- THEN 截图、SDK smoke、关键登录事件和发布回滚证据可按同一候选版本复验。

## 6. 依赖

- 前置要求：[`onboarding-and-identity-entry`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 真机与灰度商用证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：iPhone 17 截图覆盖图一/图二。
- 完成判定：`GWT-011` 对应行为满足且真实测试 `spec_ref` 有效。
