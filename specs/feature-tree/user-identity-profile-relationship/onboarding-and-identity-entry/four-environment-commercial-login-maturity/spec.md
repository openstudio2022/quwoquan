# L3 Story：四环境环境商用登录成熟度 (`four-environment-commercial-login-maturity`)

> 所属能力：[`onboarding-and-identity-entry`](../spec.md)

> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为管理身份、Persona 或关系的用户，
我希望application contract 覆盖 provider 失败、正常排队和错误验证码拒绝，
从而安全地维持身份、画像与关系状态。

## 2. 范围与非目标

### In Scope

- “四环境环境商用登录成熟度”的输入、可观察主路径、失败语义以及与父能力的交接。
- 三类外部依赖防腐接口与分环境 fail-closed 配置。
- alpha/beta/gamma `ext.sms.local_capture` 随机 OTP 协议替代 Provider 与 prod 正式 Provider 的构建、凭据和运行隔离。
- 删除任意验证码、debugCode、sandbox phone allowlist 与 pass-through 旁路。
- LoginWithSocialProvider 微信/支付宝/QQ 票据置换与首登资料同步。
- LoginWithAlipay / LoginWithQq metadata 契约与 codegen。
- 手机号 OTP 发码的单轨幂等、异步投递结果回流、端侧短期恢复与 iOS/Android 双端异常恢复。
- 手机号页 OTP delivery readiness、验证码页单一信息投影、安全系统自动填充与模拟器受保护输入能力。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 四环境环境商用登录成熟度

- application contract 覆盖 provider 失败、正常排队和错误验证码拒绝。

<a id="req-002"></a>
### REQ-002 短信 OTP challenge、密封传输与受保护随机码读取不泄漏

- application contract 覆盖 provider 失败、正常排队和错误验证码拒绝。
- API integration 证明 response/outbox 不泄露验证码，provider 只在请求前于内存中解封。
- 手机号输入可在 UI 保持大陆 11 位展示，但 `SendOtp`、`LoginWithPhone` 与手机号绑定 command 的 wire 值必须在命令边界一次性规范为 E.164；Provider Adapter 只接收同一 canonical recipient，禁止让替代实现双格式兼容。
- alpha/beta/gamma 只能由环境 Binding 选择独立 `ext.sms.local_capture` 接收本次随机 OTP，prod 只能选择正式 Provider；禁止运行时 selector、Debug override 或 fallback。OTP 以目标环境密钥加密、按 challenge TTL 暂存并一次性读取，固定万能码、App `debugCode` 和公开 API 回传均禁止。
- `POST /v1/debug/sms/otp/latest` 只存在于替代 Provider 内部控制面，要求目标环境 operator/UAT principal，不经 API Edge 暴露；回执、日志、指标与报告不得包含手机号明文或 OTP。

<a id="req-003"></a>
### REQ-003 社交三方票据置换分环境实现且 prod 使用官方协议

- 三类官方 provider resolver 均有确定性协议测试。
- prod 微信、支付宝、QQ 均有真实 UAT；未配置凭证只用于验证 fail-closed，不能作为完成证据。

<a id="req-004"></a>
### REQ-004 社交首登创建账号并同步昵称头像

- 社交首登必须先返回一次性手机号 binding ticket；手机号绑定完成后原子创建身份事实并签发会话，二次登录复用既有账号并恢复原 Persona。
- 首登绑定的手机号已属于另一账号时必须返回 `credential_conflict`；不得恢复或合并旧账号，不得签发 session，且 ticket/challenge 保持可恢复，使用户可以更换手机号继续。
- owner、primary persona、credential 与昵称头像初始化结果可在真实存储验证。

<a id="req-005"></a>
### REQ-005 端侧社交登录命中 metadata 且失败不回环

- App 端社交登录 Repository、NativeAuthBridge 和 LoginPage 状态均有 local_contract 覆盖。
- 授权取消、provider 不可用和服务错误不会触发登录回环。
- 同一次失败不会同时显示 Toast/Snackbar 与内联反馈。
- 社交授权、授权失败、手机号绑定与绑定 OTP 使用同一 `/login` 内部状态；绑定未完成时返回或杀进程均不能进入应用。

<a id="req-006"></a>
### REQ-006 社交 metadata/codegen/错误码契约一致

- LoginWithAlipay / LoginWithQq 为 public operation 且 request/response 由 metadata 生成。
- CredentialType 枚举包含 alipay/qq。
- USER.AUTH 社交错误码生成 Dart/Go 常量。
- 端侧 RemoteAuthRepository 消费生成的 path/pageId，不硬编码。
- Apple 与 Passkey 不在 public operation、RemoteAuthRepository 或用户服务公开登录路由中； `POST /auth/login/apple` 和 `POST /auth/login/passkey` 必须返回 404。
- SendOtp、手机号、微信、QQ、支付宝、一键登录和 hint 的 commercial/security/privacy/reliability/telemetry/SLO 均由 ContractGraph 生成；缺生产证据的 provider 必须保持 blocked。

<a id="req-007"></a>
### REQ-007 凭证唯一性约束契约

- 全局 credential_type+credential_key 唯一。
- owner 内 owner_id+credential_type 唯一。

<a id="req-008"></a>
### REQ-008 登录商业可观测、采样与保留契约

- 登录漏斗、各 provider 请求结果、非 2xx 比率、P95 与 USER 错误码在同一 L2 大盘可查。
- 发码指标必须至少区分 `accepted / idempotent_replay / delivery_confirming / sent_unconfirmed / delivery_failed / rate_limited / decode_contract_violation / login_success`，并监控 Provider 结果延迟、15 秒未知率、发码失败率和登录完成率。
- provider 非 2xx 比率超过 2%，或挑战/登录 P95 超过 1.2s/1.5s，连续两个 5 分钟窗口后触发告警。
- `sys.user.auth.success_detail_sample_ratio` 只拥有登录成功明细采样策略并支持 progressive rollout；物理 Logstore 保留期只引用 product-ops `event_record/storage.yaml`，user-service 不复制或覆盖。
- 登录观测不得依赖已退役的 product-ops `event_records` Mongo 集合；运行时采样和 product-ops 保留合同必须由正式单轨实现证明。

<a id="req-009"></a>
### REQ-009 四环境端到端与商用纯净证据

- alpha/beta/gamma App 使用同一 Remote user-service composition，并分别通过 target-scoped `ext.sms.local_capture` 的正式 OTP challenge 创建 canonical UserAccount；四环境 App package graph 均不可达固定码实现或端侧登录 mock。
- alpha/beta/gamma 的 SMS Binding 固定为 `ext.sms.local_capture`，prod 固定为正式 Provider；不允许在同一候选运行时切换 Provider 或回退本地认证实现。
- prod 微信、支付宝、QQ 与三网本机号认证均有真实成功证据，且无放通、无验证码回传、无 mock 数据源。
- 社交首登资料同步真机可见。
- 配置纯度门禁阻断已退休认证旁路。

<a id="req-010"></a>
### REQ-010 运营商一键：OneTapPhoneResolver 使用部署注入的运营商能力；未接入时返回结构化不可用

- 运营商一键：`OneTapPhoneResolver` 使用部署注入的运营商能力；未接入时返回结构化不可用。
- 端侧 capability 必须区分 `available / notConfigured / clientNotInstalled / probeTimeout / sdkUnavailable / unsupportedPlatform`。未安装客户端或瞬时探测失败时入口保持可发现并就近解释。
- 明确不支持的平台隐藏。
- alpha/beta/gamma target-scoped local-capture 配置缺失、或 prod 正式 Provider 配置/SDK 缺失，均由发布门禁阻断，不能靠静默隐藏伪装可用。
- local-capture 替代 Provider 的证据标记 `nonPromotable=true`：它可证明 Alpha/Beta/Gamma 边界内端云 E2E 与替代协议一致性，但不能提升真实外部 Provider 集成或 Prod readiness。
- 非生产 OTP 只允许通过当前环境 Binding 与保护身份池产生确定性的非生产账号会话；OTP 和非生产 Provider 材料不得进入仓库、receipt、prod 构建图、SBOM 或运行配置。
- provider 模式的内部短信提交仅允许 service principal + operation scope：alpha/beta/gamma local-capture 使用 HTTPS、target-scoped bearer 与目标 CA，prod 正式 Provider 使用受保护 mTLS/credential material；各自材料由 Secret Manager/CI 注入，缺失时拒绝装配远端 OTP client。
- 端侧文案统一走云端 userMessage 优先 → `UserErrorCode` baseline → 通用兜底；不直接读取原始异常字符串。
- user-service 客户端响应和日志必须脱敏 OAuth URL、authCode、token、secret 与 provider 原始 body；客户端默认不接收 debugMessage。
- `SendOtp`、手机号、微信、QQ、支付宝、一键登录与 hint 操作必须在 metadata 同源声明 commercial/security/privacy/reliability/telemetry/SLO；正式 provider 未取得生产凭据、受控 SDK 与真机 UAT 时保持 `blocked`，不得用本地协议测试改写为 ready。
- 当前只完成 `sys.user.auth.success_detail_sample_ratio` 配置契约与环境种子；事件 TTL 由 product-ops `event_record/storage.yaml` 统一拥有。在 product-ops 运行时消费采样比例的证据补齐前，不得把静态配置声明视为采样策略已生效。
- 微信、QQ、支付宝、阿里云一键登录在生产凭据、受控 SDK、真实网络真机 UAT、provider 后台结果与回滚演练齐全前保持 `GATE_BLOCK`。
- prod 用户协议/隐私政策必须由法务/运营提供真实获批主体信息并通过 legal-static CLI 生成与线上 URL 探测；不得猜测主体、地址、电话、ICP备案号，也不得把占位包当作登录商用证据。

<a id="req-011"></a>
### REQ-011 手机号 OTP 发码幂等、投递回流与端侧可恢复登录

- `SendOtp` 必须要求不含手机号的随机 128-bit `Idempotency-Key`，总 deadline 为 3 秒、最多 2 次幂等传输尝试；同 key 重放只返回原 challenge、原 delivery request、当前投递状态和精确冷却剩余，不重复计数或投递。
- 不同 key 在 60 秒冷却期返回 `otp_rate_limited` 与精确剩余秒数；同 key 跨手机号、purpose 或 binding scope 复用返回 typed `otp_idempotency_conflict`。
- 成功响应始终包含 `retryAfterSeconds`；`deliveryStatus` 是 `queued / sent_unconfirmed / delivered / failed` 闭集，不允许以自由字符串或缺字段响应逃逸。
- `AuthenticationChallenge` 在同一权威行保存 `deliveryRequestId / deliveryStatus / deliveryUpdatedAt / lastDeliveryEventId`；User Service 只通过 `ExternalInteractionResultReported` durable consumer 接收最终 Provider 结果，重复、乱序和终态倒退均为幂等 no-op。明确 `failed / dead_letter` 必须原子标记投递失败并取消仍 pending 的 challenge。
- App 将 OTP 投递状态与验证码验证状态分离。发送网络错误、响应超时或未知结果必须进入验证码页并允许输入已收到的验证码；5 秒、15 秒及恢复前台时用同一 key 做有界确认，15 秒后停止自动确认而不显示无限 spinner。
- App 在安全存储中只保存 5 分钟有效的 PendingOtpAttempt（手机号、脱敏手机号、key、challenge/request ID、状态与倒计时），永不保存 OTP。冷启动可恢复同一验证码页；登录成功、更换手机号、过期或退出流程必须清除。
- `LoginWithPhone` 网络错误或响应超时必须保留完整 6 位验证码和“重新验证”动作；服务端对同凭据重复验证 completed challenge 返回同一成功语义且不增加失败次数。
- `confirming / queued` 使用中性提示并通过 live region 播报，只有明确失败使用错误色；忙碌状态同时显示 spinner 与文字。iOS/Android 均保留 `oneTimeCode` 自动填充和第六位自动验证。

<a id="req-012"></a>
### REQ-012 手机号登录可理解恢复、发码就绪门与安全自动填充

- 手机号页必须通过公开只读 `GetOtpDeliveryReadiness` 在发码前确认认证投递链可用；检查进行时不阻止输入，`temporarily_unavailable`、网络失败或超时均留在手机号页并只显示 `登录服务暂时不可用，请稍后重试`，用户点击 `重试` 只重新检查，不暗中发码。
- 验证码页只能消费一个 `OtpPagePresentation`。账号终态、验证中、验证错误、明确发码失败、发码进度和普通输入引导按固定优先级投影为至多一条提示与一组恢复动作；禁止同时渲染 delivery notice 和 verification feedback。
- 用户可见文案不得出现“结果确认”“状态保留”“challenge”“Provider”“requestId”等内部概念，并删除黄色未知状态。说明文字不可点击，恢复动作必须是最小 44pt 的明确按钮。脱敏手机号与“更换手机号”同一行，恢复动作不与底部第三方登录混排。
- 验证码错误清空并聚焦第一格；验证网络失败或超时只在当前页面内存中保留可见的六位输入并提供唯一 `重新验证` 动作，不把 OTP 写入 PendingOtpAttempt。倒计时结束后才并排提供 `重新验证 / 重新获取`。
- 第六位输入、粘贴、iOS 系统 AutoFill 与 Android Retriever 均只能触发一次验证；用户修改输入即清除旧错误。登录成功、更换手机号、过期或退出时停止监听并清理 challenge、key、倒计时和提示。
- iOS 只使用 `oneTimeCode` 与 domain-bound SMS 的系统建议，不申请或读取短信权限。Android 只使用 SMS Retriever，不申请 `READ_SMS / RECEIVE_SMS`；只接受当前 `requestId` 对应的非敏感 `requestRef`、六位码和候选签名绑定 app hash，旧短信、错 ref、重复消息均忽略。
- `SendOtpCommand.platform` 必须是 `ios / android / web / acceptance` typed enum。短信 domain、Android app hash 和模板由候选绑定的服务端可信配置选择，客户端不得上传这些值。
- 模拟器登录只经 typed `PHONE_OTP_LOGIN_TARGET` capability：Android Emulator 通过受管 adapter 注入完整 SMS 并实际经过 Retriever；iOS Simulator 只能由 protected broker 一次性交给 Patrol 输入框，CaseResult 必须标记 `inputMode=protected_harness`，不得冒充 iOS SMS AutoFill。

## 4. 契约引用

- canonical：`quwoquan_service/services/user-service/environments/gamma/config.yaml`
- canonical：`quwoquan_service/services/user-service/environments/prod/config.yaml`
- canonical：`quwoquan_service/scripts/user-service/verify_login_dependency_config.py`
- canonical：`quwoquan_service/services/user-service/tests/local_contract/account/authentication_challenge/command_facade__local_contract_test.go`
- canonical：`quwoquan_service/services/user-service/tests/api_integration/account/user_account/helpers__support__api_integration_test.go`
- canonical：`quwoquan_service/services/integration-service/tests/api_integration/external_integration/external_interaction/external_interaction_mongo_provider__reliability__api_integration_test.go`
- canonical：`quwoquan_service/services/user-service/contracts/account/account_session/operations.yaml`
- canonical：`quwoquan_service/services/user-service/contracts/account/account_session/errors.yaml`
- canonical：`quwoquan_service/services/user-service/contracts/account/authentication_challenge/operations.yaml`
- canonical：`quwoquan_service/services/user-service/contracts/account/credential_binding/operations.yaml`
- canonical：`quwoquan_service/services/user-service/contracts/account/credential_binding/errors.yaml`
- canonical：`quwoquan_service/services/user-service/contracts/account/user_account/fields.yaml`
- canonical：`quwoquan_service/services/user-service/tests/api_integration/account/user_account/auth_contract__api_integration_test.go`
- canonical：`quwoquan_app/test/local_contract/service/user_service/account/account_session/login_page_widget__local_contract_test.dart`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 四环境环境商用登录成熟度

- GIVEN 管理身份、Persona 或关系的用户具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“四环境环境商用登录成熟度”对应的公开行为。
- THEN application contract 覆盖 provider 失败、正常排队和错误验证码拒绝。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

<a id="gwt-003"></a>
### GWT-003 社交三方票据置换分环境实现且 prod 使用官方协议

- GIVEN 微信、支付宝或 QQ 的有效或失败票据在支持环境中提交。
- WHEN 对应 provider resolver 执行置换。
- THEN 非生产使用受控环境配置，prod 只使用官方协议，且未配置凭据时 fail-closed。

<a id="gwt-009"></a>
### GWT-009 四环境端到端与商用纯净证据

- GIVEN alpha、beta、gamma 与 prod 分别构建并执行登录路径。
- WHEN 验证 alpha/beta/gamma local-capture 随机 OTP 的受保护一次性读取、prod 正式 Provider、首登资料同步和失败恢复。
- THEN local-capture workload、凭据、路由与捕获存储不可达 Prod 包、SBOM 和部署图；三测试环境 Green 可由替代边界 E2E 提升，但真实 Provider 集成与 Prod readiness 只由 Prod 正式 Provider 回执和可复验真机证据提升。

<a id="gwt-011"></a>
### GWT-011 发码响应丢失、Provider 终态与冷启动恢复

- GIVEN User Service 已按唯一 key 创建 challenge 并提交短信，App 可能在响应到达前超时、退后台或被杀死。
- WHEN App 使用同一 key 自动重试、前台确认或冷启动恢复，且 Provider 随后报告成功、失败、重复或乱序结果。
- THEN 只有一个 challenge、一个 Provider request 和一次配额；用户始终可以输入已收到的验证码，明确失败和限频显示精确倒计时，未知状态在 15 秒后停止自动确认且倒计时结束后才允许用新 key 重发。
- AND 发送与验证响应丢失均可回到正常登录路径，安全存储、日志、指标和回执不包含 OTP、手机号明文或 Provider raw body。

<a id="gwt-012"></a>
### GWT-012 登录依赖不可用、验证失败与双端自动填充均有唯一恢复路径

- GIVEN 用户从手机号页开始登录，认证投递链可能停止、短信可能延迟，验证请求也可能错误、断网或超时。
- WHEN App 执行 readiness、发码、输入或系统自动填入、验证、重发与更换手机号。
- THEN 每一时刻页面至多显示一条用户可理解的提示和一组不重复的恢复按钮；依赖不可用不进入验证码页，结果未知不显示黄色警告，验证码错误可立即重输，网络失败可直接重新验证。
- AND iOS 真机只消费系统验证码建议，Android 真机只消费与当前 requestRef 精确绑定的 Retriever 消息；模拟器证据诚实区分 protected harness 与真实短信 AutoFill，任一路径均只提交一次且不泄露手机号或 OTP。

## 6. 依赖

- 前置要求：[`onboarding-and-identity-entry`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 社交三方票据置换分环境实现且 prod 使用官方协议

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：三类官方 provider resolver 均有确定性协议测试。
- 完成判定：`GWT-003` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-002"></a>
### OPEN-002 登录成功明细采样控制面闭环

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 当前事实：登录漏斗、操作失败率、状态停留、绑定放弃率已进入 L2 大盘与告警；物理保留统一服从 product-ops `event_record/storage.yaml`，不再由 user-service 声明第二套 TTL。
- 影响或价值：尚缺 product-ops 正式运行时消费 `sys.user.auth.success_detail_sample_ratio` 的实现与环境验收证据；成功运维明细仍按事件目录全量采集，静态配置尚不能证明采样策略生效。
- 目标：在不削弱失败、terminal、stalled 事件全量观测和 Prometheus 分母的前提下，由正式配置单轨驱动登录成功明细的确定性采样。
- 完成判定：运行时读取 `sys.user.auth.success_detail_sample_ratio`，成功明细按稳定键确定性采样，失败、terminal、stalled 保持 100%，并由 local contract、环境配置探针和聚合指标证明实际采样率与回滚路径。

<a id="open-003"></a>
### OPEN-003 四环境端到端与商用纯净证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：alpha App 通过 Remote user-service 与受管非生产 Provider 的正式 OTP challenge 创建 canonical UserAccount；四环境 App package graph 不可达固定码实现或端侧登录 mock。
- 完成判定：`GWT-009` 对应行为满足且真实测试 `spec_ref` 有效。
