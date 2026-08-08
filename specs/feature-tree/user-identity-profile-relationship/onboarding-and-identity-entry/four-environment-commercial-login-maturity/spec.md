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
