# L3 Story：four-environment-commercial-login-maturity

## 功能说明

本 Story 把全部登录方式（手机号验证码、运营商一键登录、微信、支付宝、QQ、匿名/游客）收敛到**同一套“环境 × 外部依赖”配置契约**下。短信 OTP、运营商号码置换和社交 OAuth 都经防腐接口进入 provider；环境差异只来自受控装配、部署凭据和拓扑。alpha/beta/gamma 允许确定性的固定测试 OTP provider，但不得引入任意验证码放通、验证码回传或可进入 prod 的 Mock 旁路。

本 Story 不替代 `two-state-one-tap-login--commercial-login-entry`（登录页骨架与手机号/一键的体验验收），而是在其之上补齐：社交三方真实置换、四环境矩阵、首登资料同步、凭证唯一性与 fail-closed 准入。

## 用户价值

- 用户可用微信/支付宝/QQ 一键登录，首次登录自动同步第三方昵称与头像到本应用，无需手动填写资料。
- 同一 OwnerAccount 可并行绑定一个微信、一个支付宝、一个 QQ（每类型至多一个），跨类型可同时绑定。
- 所有环境的验证码都经 challenge 校验；端云 response、日志和 UI 均不接收或显示验证码。
- alpha/beta/gamma 默认固定测试码 `123456`，但仍执行有效期、限流、失败与一次性消费；prod 无认证放通后门、无 mock 数据源，登录链路失败时保持 fail-closed。

## 范围

- 三类外部依赖防腐接口与分环境部署配置：
  - 短信 OTP：`ExternalInteractionClient` 负责受控投递；验证码只保存 challenge hash，投递明文通过短时密封 `codeRef` 进入 provider 内存。
  - 运营商一键：`OneTapPhoneResolver` 使用部署注入的运营商能力；未接入时返回结构化不可用。
  - 社交 OAuth：`ExternalAuthProviderClient` 只装配真实 HTTP provider；凭据缺失时 fail-closed。
- user-service 社交票据置换：`LoginWithSocialProvider`（wechat/alipay/qq），稳定 credentialKey（unionId 优先），首登创建 owner + primary persona + credential，首登资料同步昵称/头像与昵称去重。
- 端云契约：`service.yaml` 新增 `LoginWithAlipay`/`LoginWithQq`，`fields.yaml` 扩展 `CredentialType`（alipay/qq），`errors.yaml` 新增社交错误码，codegen 产出 Go/Dart。
- 端侧：`AuthRepository.loginAlipay/loginQq`、`NativeAuthBridge`、`LoginPage` 三方登录状态流与无死循环；`OtpSendResultData` 不含验证码。
- 四环境 `config.yaml` 矩阵与门禁：`verify_login_dependency_config.py` 阻断已退休认证旁路。

## Out of Scope

- 不实现 Apple、Passkey 的正式 SDK 登录；仅保留未来扩展所需的防腐层枚举，不提供 App 登录入口、Remote Repository 方法或公开 HTTP 登录路由。
- 不做第三方头像转存自有 CDN（首登先存厂商头像 URL，留待 media 资产管线）。
- 不引入第二套登录页或登录路由。

## 四环境 × 三类外部依赖矩阵（真相源）

| 依赖 \ 环境 | alpha | beta | gamma | prod |
|---|---|---|---|---|
| 短信 OTP 下发 | public plane / alpha runner 固定测试码 `123456` | 默认固定测试 provider，可显式切沙箱/真实 provider | 默认固定测试 provider，可显式切沙箱/真实 provider | 仅真实 provider，缺配置启动失败 |
| 运营商一键 | App alpha runner contract fixture，不请求 user-service | 部署注入的 resolver，缺失启动失败 | 部署注入的 resolver，缺失启动失败 | 部署注入的 resolver，缺失启动失败 |
| 社交 OAuth | App alpha runner contract fixture，不请求 user-service | 真实 HTTP provider，缺配置启动失败 | 真实 HTTP provider，缺配置启动失败 | 微信/支付宝/QQ 正式 SDK 与服务端官方签名/令牌置换；缺配置启动失败 |

- 端侧 capability 必须区分 `available / notConfigured / clientNotInstalled / probeTimeout / sdkUnavailable / unsupportedPlatform`。未安装客户端或瞬时探测失败时入口保持可发现并就近解释；明确不支持的平台隐藏；beta/gamma/prod 配置或 SDK 缺失由发布门禁阻断，不能靠静默隐藏伪装可用。
- 固定测试 OTP 只允许产生确定性的非生产账号会话；非生产 provider 与固定码不得进入 prod 构建图、SBOM 或运行配置。
- provider 模式的内部短信提交仅允许 service principal + operation scope + HTTPS/mTLS；`INTEGRATION_SERVICE_MTLS_CA_FILE`、`INTEGRATION_SERVICE_MTLS_CLIENT_CERT_FILE`、`INTEGRATION_SERVICE_MTLS_CLIENT_KEY_FILE` 由 Secret Manager/CI 注入，缺失时拒绝装配远端 OTP client。

## 凭证与唯一性

- 全局唯一：`credential_type + credential_key`（一个第三方身份只能绑定一个 owner）。
- owner 内唯一：`owner_id + credential_type`（一个 owner 每类型至多一个绑定）。
- credentialKey 由服务端基于 `ExternalIdentity` 生成：优先 `provider:unionid:<unionId>`，否则 `provider:appopenid:<appId>:<openId>`；App 不上传持久厂商账号 ID。

## 首登资料同步

- 首次社交登录创建 owner + primary persona 后，用厂商公开资料初始化：`ownerDisplayName`、`nickname`、`nicknameCustomized=true`、`avatarUrl`（暂存厂商 URL）。取得头像字段不等于端侧展示成功；登录页仅在现有可信 CDN/gateway 候选成功解码后显示头像，原始第三方 URL 不新增白名单。
- 同步失败不阻断登录：结构化告警 + 默认资料兜底。

## 错误与异常语义

- 社交错误码：`USER.AUTH.wechat_auth_failed` / `alipay_auth_failed` / `qq_auth_failed`（502 retry）、`social_provider_cancelled`（400 surface）、`social_provider_unavailable`（503 surface）。
- 端侧三方登录失败只在社交方法区域提示并保持登录页可重试；取消由恢复策略吸收且不显示错误，绝不在受限态二次弹登录。
- 运营商入口采用 `OneTapAvailability` 强类型探测；只有 vendor、短时 token 与有效期组成完整可提交路径时才可见。仅 SDK 初始化、未配置、超时、网络不支持和无 token 探测均静默回退短信，不以用户点击后的失败探测能力。
- 端侧文案统一走云端 userMessage 优先 → `UserErrorCode` baseline → 通用兜底；不直接读取原始异常字符串。
- user-service 客户端响应和日志必须脱敏 OAuth URL、authCode、token、secret 与 provider 原始 body；客户端默认不接收 debugMessage。

## 观测、SLO 与灰度

- KPI：各社交 provider 登录成功率、首登资料同步成功率、provider 失败率与凭据配置失败次数。
- SLO：社交票据置换 P95 <= 1500ms；首登资料同步 P95 <= 1000ms（异步不阻断登录）。
- 灰度：社交入口和 provider vendor 可按环境/版本/渠道控制；回滚到"仅手机号 + 一键"，不引入身份旁路。
- `SendOtp`、手机号、微信、QQ、支付宝、一键登录与 hint 操作必须在 metadata 同源声明 commercial/security/privacy/reliability/telemetry/SLO；正式 provider 未取得生产凭据、受控 SDK 与真机 UAT 时保持 `blocked`，不得用本地协议测试改写为 ready。
- 登录商业大盘与 Alertmanager 规则复用 `http_server_*` / `http_server_error_codes_total` 实际指标；provider 错误率 >2% 或 P95 超标连续两个 5 分钟窗口后告警。原始登录明细 30 天、聚合指标 180 天，成功明细 prod 默认采样 10%，均由 `sys.user.auth.*` 配置治理。
- 当前只完成上述 `sys.user.auth.*` 配置契约、环境种子和事件 TTL；在 product-ops 运行时消费采样比例并形成 180 天聚合保留的证据补齐前，不得把静态配置声明视为采样策略已生效。

## 当前商业准入状态

- 当前为 `GATE_BLOCK`。`R-AUTH-001` 在微信、QQ、支付宝、阿里云一键登录的生产凭据、受控 SDK、真实网络真机 UAT、provider 后台结果与回滚演练齐全前不得关闭。
- prod 用户协议/隐私政策必须由法务/运营提供真实获批主体信息并通过 legal-static CLI 生成与线上 URL 探测；不得猜测主体、地址、电话、ICP备案号，也不得把占位包当作登录商用证据。
- 静态仪表盘/告警/配置契约只证明工程接线存在；没有真实运行窗口、告警触发与回滚演练时，SLO 证据仍为 partial。

## 验收标准

- A1：四环境矩阵在 config 与门禁中冻结；已退休认证旁路在任一环境出现即被阻断。
- A2：社交三方（wechat/alipay/qq）端云链路只使用真实 provider；缺凭证只允许 fail-closed，不以 unavailable 作为商用完成证据。
- A3：首登创建 owner/persona/credential 并同步昵称头像，昵称去重生效。
- A4：凭证全局唯一与 owner 内每类型唯一约束生效。
- A5：端侧 `loginAlipay/loginQq` 命中 metadata path/pageId，社交登录失败/取消不回环。
- A6：`SendOtp` API、端侧数据模型和 UI 均不包含验证码。
- A7：mock 隔离、平台分支隔离、登录无死循环门禁全绿。
- A8：同一社交失败只有一个就近反馈，取消静默恢复；客户端与日志无 secret、authCode、token 和 OAuth URL 泄露。
