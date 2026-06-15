# L3 Story：four-environment-commercial-login-maturity

## 功能说明

本 Story 把全部登录方式（手机号验证码、运营商一键登录、微信、支付宝、QQ、匿名/游客）收敛到**同一套"环境 × 外部依赖"注入矩阵**下，使 alpha/beta/gamma/prod 四个环境都可端到端走通、可测试且可商用发布。核心是为三类外部依赖（短信 OTP 下发、运营商号码置换、社交 OAuth 置换）建立**统一防腐接口 + 分环境实现注入**：mock（离线确定性，发布安全）、sandbox（受控放通）、real（真实上游），并以门禁强制生产严格、非生产可测。

本 Story 不替代 `two-state-one-tap-login--commercial-login-entry`（登录页骨架与手机号/一键的体验验收），而是在其之上补齐：社交三方真实置换、四环境矩阵、gamma 受控放通、首登资料同步、凭证唯一性。

## 用户价值

- 用户可用微信/支付宝/QQ 一键登录，首次登录自动同步第三方昵称与头像到本应用，无需手动填写资料。
- 同一 OwnerAccount 可并行绑定一个微信、一个支付宝、一个 QQ（每类型至多一个），跨类型可同时绑定。
- 测试/灰度人员在 gamma 用沙箱白名单测试号/测试授权码即可走真实链路验证，普通真实用户仍受严格校验保护。
- 生产环境无任何放通后门、无 debugCode、无 mock 数据源，登录链路纯净可商用。

## 范围

- 三类外部依赖防腐接口与分环境注入：
  - 短信 OTP：`ExternalInteractionClient`（real）+ `SmsOtpPassThroughConfig`（alpha/beta 全局放通）+ `SandboxAllowlist`（gamma 受控放通）。
  - 运营商一键：`OneTapPhoneResolver`（alpha/beta dev 解码 / gamma 沙箱静态号段 / prod 真实运营商，未接入前返回结构化不可用，杜绝 dev 后门进生产）。
  - 社交 OAuth：`ExternalAuthProviderClient`（alpha/beta mock / gamma sandbox 包装 real / prod real HTTP）。
- user-service 社交票据置换：`LoginWithSocialProvider`（wechat/alipay/qq），稳定 credentialKey（unionId 优先），首登创建 owner + primary persona + credential，首登资料同步昵称/头像与昵称去重。
- 端云契约：`service.yaml` 新增 `LoginWithAlipay`/`LoginWithQq`，`fields.yaml` 扩展 `CredentialType`（alipay/qq），`errors.yaml` 新增社交错误码，codegen 产出 Go/Dart。
- 端侧：`AuthRepository.loginAlipay/loginQq`、`NativeAuthBridge`（含 wechat/alipay/qq + `SandboxNativeAuthBridge`）、`LoginPage` 三方登录状态流与无死循环、`shouldRevealOtpDebugCode` 扩展 gamma 受控放通。
- 四环境 `config.yaml` 矩阵与门禁：`verify_sms_otp_pass_through_gate.py` 允许 gamma 受控放通、强制 prod 严格。

## Out of Scope

- 不实现 Apple、Passkey 的正式 SDK 登录（保留既有占位接口）。
- 支付宝/QQ 的 prod 真实 OAuth 置换需各自签名/令牌流程，未注入完整 app 凭证前 `HTTPExternalAuthProviderClient` 返回结构化 `social_provider_unavailable`，绝不伪造成功（登记 `TECHDEBT-SOCIAL-PROD-OAUTH-ALIPAY-QQ-001`）。
- 不做第三方头像转存自有 CDN（首登先存厂商头像 URL，留待 media 资产管线）。
- 不引入第二套登录页或登录路由。

## 四环境 × 三类外部依赖矩阵（真相源）

| 依赖 \ 环境 | alpha | beta | gamma | prod |
|---|---|---|---|---|
| 短信 OTP 下发 | 全局放通 + debugCode | 全局放通 + debugCode（真实 user-service + mock integration） | 真实上游 + 受控放通（沙箱号段回填 debugCode，非白名单严格） | 真实下发，无放通、无 debugCode |
| 运营商一键 | dev token 解码 | dev token 解码 | 沙箱静态号段（`sandbox-onetap-token-*`），无号段则不可用 | 真实运营商 resolver（未接入前结构化不可用，无 dev 后门） |
| 社交 OAuth | mock（离线确定性身份） | mock（离线确定性身份） | sandbox 包装 real（`sandbox-<provider>-*` 返回沙箱身份，其余委托 real HTTP） | real HTTP（微信标准流程；支付宝/QQ 待凭证，未配置返回 unavailable） |

- 端侧对称：`nativeAuthBridgeProvider` 在 alpha/beta/gamma 注入 `SandboxNativeAuthBridge`（返回 `sandbox-<provider>-` 票据，发布安全、不出网），prod 注入真实 `MethodChannelNativeAuthBridge`（mobile）或结构化 unavailable（web/ohos/desktop）。
- gamma 受控放通与全局放通的区别：全局放通对所有号码生效且仅非生产；受控放通仅命中白名单 entry 生效，gamma 对接真实上游但保留可测性，prod 必须为空。

## 凭证与唯一性

- 全局唯一：`credential_type + credential_key`（一个第三方身份只能绑定一个 owner）。
- owner 内唯一：`owner_id + credential_type`（一个 owner 每类型至多一个绑定）。
- credentialKey 由服务端基于 `ExternalIdentity` 生成：优先 `provider:unionid:<unionId>`，否则 `provider:appopenid:<appId>:<openId>`；App 不上传持久厂商账号 ID。

## 首登资料同步

- 首次社交登录创建 owner + primary persona 后，用厂商公开资料初始化：`ownerDisplayName`、`nickname`（去重：被占用则追加 owner 熵尾后缀）、`avatarUrl`（暂存厂商 URL）。
- 同步失败不阻断登录：结构化告警 + 默认资料兜底。

## 错误与异常语义

- 社交错误码：`USER.AUTH.wechat_auth_failed` / `alipay_auth_failed` / `qq_auth_failed`（502 retry）、`social_provider_cancelled`（400 surface）、`social_provider_unavailable`（503 surface）。
- 端侧三方登录失败/取消只就近提示并保持登录页可重试，绝不在受限态二次弹登录（遵循登录入口无死循环宪法）。
- 端侧文案统一走云端 userMessage 优先 → `UserErrorCode` baseline → 通用兜底；不直接读取原始异常字符串。

## 观测、SLO 与灰度

- KPI：各社交 provider 登录成功率、首登资料同步成功率、gamma 受控放通命中率、prod 社交 unavailable 占比。
- SLO：社交票据置换 P95 <= 1500ms；首登资料同步 P95 <= 1000ms（异步不阻断登录）。
- 灰度：社交入口、provider vendor、受控放通白名单均可按环境/版本/渠道控制；回滚到"仅手机号 + 一键"。

## 验收标准

- A1：四环境矩阵在 config 与门禁中冻结；gamma 受控放通合法、prod 严格，门禁阻断回归。
- A2：社交三方（wechat/alipay/qq）端云链路在 alpha/beta/gamma 端到端走通（mock/sandbox），prod wechat 真实、alipay/qq 结构化 unavailable。
- A3：首登创建 owner/persona/credential 并同步昵称头像，昵称去重生效。
- A4：凭证全局唯一与 owner 内每类型唯一约束生效。
- A5：端侧 `loginAlipay/loginQq` 命中 metadata path/pageId，社交登录失败/取消不回环。
- A6：`shouldRevealOtpDebugCode` 仅 gamma 受控放通（`deliveryStatus == 'sandbox'`）回填，prod 永不回填。
- A7：mock 隔离、平台分支隔离、登录无死循环门禁全绿。
