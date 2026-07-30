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

- 一键、手机号、OTP、异常、第三方授权与绑定手机号共享同一 `LoginFrame`：顶部导航、可滚动正文、固定第三方登录 footer。
- 一键入口依次为“本机号码一键登录”“其他手机号登录”、协议确认和微信/QQ/支付宝 footer；手机号不进入 footer。
- 标题、副标题、状态、错误、倒计时、文字动作与协议整体居中；手机号输入左对齐，OTP 数字格内居中。
- 移动、平板、Web、键盘、横屏与 200% 字体下关键区域不重叠、不拉伸、不漂移，footer 不随正文状态切换改变基线。

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

- 发码成功后同一位置从“60秒后可重新获取”递减到“1秒后可重新获取”，归零后替换为“重新获取验证码”；同一倒计时周期只能触发一次重发。
- 输入、粘贴或系统自动填充第六位后自动验证一次，验证中锁定输入并显示“正在验证”，不显示额外登录按钮。
- OTP 状态在同一布局骨架内完成，不发生控件错位；后台恢复按绝对截止时间重新计算倒计时。

<a id="req-007"></a>
### REQ-007 手机号验证码异常不拦截用户

- `otp_mismatch` 只显示红色“验证码不正确”，六格轻抖一次、清空并将焦点回到第一格；验证码格永不变红且原倒计时继续。
- `otp_expired/challenge_consumed` 显示“验证码已失效”，`otp_attempts_exceeded/rate_limited` 显示“尝试次数较多”，`otp_provider_failed` 显示“验证码发送失败”；恢复动作与错误文案分离。
- 网络校验失败保留验证码并显示“暂时无法验证验证码”与“重新验证”。
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
- otp mismatch 清空验证码并允许立即重新输入，otp expired 进入重新获取；两者均不重置仍有效的重发冷却截止时间。
- 每个 USER.AUTH 错误码都有 recovery.action、disruptionLevel、双语文案与唯一 LoginErrorSurface。
- RuntimeErrorResponse 不向客户端返回 debugMessage、authCode、token、secret 或 provider 原始 URL。
- 登录产品漏斗与运维失败事件分轨；运维事件以 `sourceCode/failureKind/recoveryAction/copyKey/feedbackSurface/requestId/traceId` 还原错误与用户提示，任一事件均不得包含手机号、OTP、binding ticket、token 或 provider 原始票据。

<a id="req-011"></a>
### REQ-011 真机与灰度商用证据

- iPhone 17 截图覆盖图一/图二。
- iPhone 17 截图覆盖手机号验证码 12 状态。
- Android/iOS 运营商 SDK smoke 覆盖可用与不可用。
- Android/iOS 短信 provider smoke 覆盖发送成功、频控和失败。
- Web/iPad 截图覆盖居中 frame。
- 登录页曝光、状态解析、主按钮点击、成功、失败、关闭埋点可查。
- 五组高保状态在 light/dark 下逐状态可复验，显式文字对齐要求优先于生成图中不一致的左对齐或临时图标效果。
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
- 普通登录步骤不展示营销 Hero 或应用图标；仅第三方授权和绑定步骤展示当前 provider 官方图标。
- 验证码必须显示为 6 个独立方框；隐藏输入只能用于焦点、粘贴和键盘控制，普通输入框不得外露。
- 所有异常态必须就近提示，并保留关闭、修改手机号、重试或切换其它方式的清晰路径。手机号格式使用字段错误。
- 验证码、发送、限流、过期与社交失败使用居中的“红色事实 + 蓝色动作 + 灰色等待”语义，不使用错误卡重复操作指令。
- 同一次失败只允许一个可见反馈。

<a id="req-013"></a>
### REQ-013 单一正交状态与 terminal latch

- `/login` 内部步骤固定为 `resolving/oneTap/phoneEntry/otp/socialAuthorizing/socialFailed/socialPhoneEntry/socialPhoneOtp/blocked/completing`，异步 operation、consent、challenge 与 feedback 分别建模。
- 任一 busy 状态必须有超时、取消或失败出口；迟到回调不得覆盖当前步骤。
- 登录成功、关闭和异步竞争只能完成一次 terminal callback；内部返回回到上一登录步骤，根步骤关闭遵守宿主 `LoginDismissPolicy`。

<a id="req-014"></a>
### REQ-014 社交首登手机号绑定不可绕过

- 社交登录只消费 `account_session` 的判别结果；`phoneBindingRequired` 只携带短期一次性 binding ticket，不得携带完整 session。
- binding ticket 范围内发送 `bind_phone` OTP，完成 binding ticket、OTP challenge、手机号唯一性与 consent 校验后，由 `credential_binding` 原子返回 `AuthSessionGrant`。
- 社交首登手机号若已属于另一账号，必须返回 `USER.AUTH.credential_conflict` 与“这个手机号已绑定其他账号”，不得自动恢复旧账号、合并账号或签发 session；ticket 与 challenge 保持可恢复状态，用户可更换手机号继续。
- 已登录账号在设置页执行 `BindPhoneCredential` 时继续使用不带社交 ticket 的 `bind_phone` challenge；社交 completion 只接受与自身 ticket 精确关联的 challenge，两条流程不得互相冒充。
- 用户返回、ticket 过期、进程重启或绑定失败均回到可操作登录态，不进入 Shell、不消费原动作 continuation。

## 4. 契约引用

- canonical：`quwoquan_app/test/local_contract/ui/user/login_page_widget__local_contract_test.dart`
- canonical：`quwoquan_app/test/local_contract/core/auth/auth_session_store__local_contract_test.dart`
- canonical：`quwoquan_app/test/local_contract/cloud/user/account_identity_facets__contract__local_contract_test.dart`
- canonical：`quwoquan_service/services/user-service/contracts/account/account_session/operations.yaml`
- canonical：`quwoquan_service/services/user-service/contracts/account/authentication_challenge/operations.yaml`
- canonical：`quwoquan_service/services/user-service/contracts/account/credential_binding/operations.yaml`
- canonical：`quwoquan_service/services/user-service/tests/api_integration/account/user_account/auth_contract__api_integration_test.go`
- canonical：`quwoquan_app/test/local_contract/core/widgets/app_cached_network_image__local_contract_test.dart`
- canonical：`quwoquan_app/test/local_contract/ui/user/journeys/commercial_login_recovery_journey__local_contract_test.dart`
- canonical：`quwoquan_service/services/user-service/contracts/account/account_session/errors.yaml`
- canonical：`quwoquan_service/services/user-service/contracts/account/authentication_challenge/errors.yaml`
- canonical：`quwoquan_service/services/user-service/contracts/account/credential_binding/errors.yaml`
- canonical：`quwoquan_app/test/local_contract/core/auth/auth_gate_matrix_contract__local_contract_test.dart`
- canonical：`quwoquan_app/test/local_contract/ui/user/goldens`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 两态一键登录与手机号登录

- GIVEN 管理身份、Persona 或关系的用户具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“两态一键登录与手机号登录”对应的公开行为。
- THEN 本机号码首次登录在服务端完成账号、persona、credential、device 与 consent 持久化。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

<a id="gwt-002"></a>
### GWT-002 登录高保状态与可恢复交互

- GIVEN 用户处于一键、手机号、OTP、授权、异常或绑定手机号任一步骤。
- WHEN 页面切换、验证码失败、倒计时归零、协议确认、返回或异步结果到达。
- THEN 页面保持同一骨架与 footer 基线，每个状态均有明确动作或安全退出，且 terminal callback 最多执行一次。

<a id="gwt-003"></a>
### GWT-003 社交首登绑定手机号后签发会话

- GIVEN 社交身份尚未绑定手机号。
- WHEN provider 票据校验成功并完成 `bind_phone` OTP。
- THEN binding ticket 被一次性消费，手机号与社交凭证归属同一 OwnerAccount，并且只在绑定成功后返回 `AuthSessionGrant`。
- AND 若手机号已属于另一 OwnerAccount，则返回 `credential_conflict`，不创建、不合并、不签 session；更换手机号后仍可继续完成本次绑定。

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
