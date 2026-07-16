# L3 Story：commercial-login-entry--one-tap-and-phone-otp

## 功能说明

本 Story 将登录页收敛为同一商用登录骨架下的三类入口：历史账号一键登录、本机号码一键登录/创建、其它手机号验证码登录。登录页以高保图为唯一体验目标，移动端、iPad 与 Web 共用同一视觉骨架；差异只允许出现在 Account Area，不能维护第二套登录页面或未上线兼容分支。

## 用户价值

- 老用户在换机、会话过期或软退出后，可以看到稳定的昵称与脱敏手机号；真实头像成功加载时再渐进增强账号识别，并通过服务端二次校验快速回到目标态。
- 新用户在运营商网关可用时，可以用本机号码一键创建默认账号、默认昵称与主分身，随后在“我的主页”完善资料。
- 当历史会话与运营商能力都不可用，或用户主动选择“其它手机号”时，用户可以在同一骨架内用手机号验证码完成登录，不会被异常、频控或服务商失败卡死。
- 登录原因、协议同意、关闭安全态与登录成功目标态清晰，避免“登录后不知道为什么”和“关闭后反复弹登录”。

## 范围

- `LoginPage` 的统一登录骨架、手机号 OTP 全状态高保布局、深浅色、无障碍、响应式与截图验收。
- 本地历史账号摘要：头像、昵称、脱敏手机号、身份来源、最近登录方式。
- 运营商 SDK 能力探测、授权 token 获取、脱敏手机号展示和超时降级。
- 手机号验证码：输入、发码、六格验证码、倒计时、错误、过期、频控、登录成功。
- `ResolveOneTapLoginHint`、`LoginOneTap`、`SendOtp`、`LoginWithPhone` metadata 契约、Dart/Go codegen、Remote/Mock 一致。
- user-service 运营商 token 置换、OTP 发码、账号查询/创建、默认资料生成、凭证/设备/consent 持久化。
- 登录曝光、状态解析、点击、成功、失败、关闭等埋点与 SLO。

## Out of Scope

- 微信、QQ、支付宝的正式 SDK 与服务端票据置换由 `four-environment-commercial-login-maturity` Story 负责；本 Story 只要求其入口与手机号/一键登录共享同一页面骨架和安全恢复路径。
- Apple、Passkey 当前不提供正式 SDK、App 登录入口或公开 HTTP 登录路由。
- 不保留未上线旧聚合登录 request 字段、旧 `/v1/auth/login` 别名路由或第二套 Web 登录视觉。
- Web 不承诺运营商一键登录可用；Web 仅展示同构壳并按能力位降级。

## UX 与视觉约束

- 登录页退出控件只由宿主导航语义决定，与错误状态无关：栈内入口使用返回箭头并 `popPrevious`；受限目标触发的强登录使用 `safeFallback` 关闭到公开安全态；Web/弹层宿主使用 `hostControlledClose`。错误组件不得注入 X、返回按钮或改写关闭策略。
- 登录原因只由 `AuthGateReason/AuthContinuation` 决定；返回账号、运营商和手机号状态切换不得覆盖来源标题与说明。
- 返回会话恢复与运营商一键登录是两种独立动作：前者主按钮为“继续登录”，后者仅在运营商能力完整可提交时展示“本机号码一键登录”。
- 返回账号摘要必须同时满足“可识别且可执行”：定制昵称或真实脱敏标识至少存在一项，并且存在有效 refresh、可预填手机号或可执行的记住社交方式。系统默认昵称、头像或“上次使用的账号”等占位不得单独创建返回账号态。
- 三入口同构：Logo、品牌、主标题、副标题、主按钮、协议区、其他登录方式位置和高度一致。
- 返回账号态把头像作为渐进增强：只有可信候选成功下载并解码后才显示 72px 圆形真实头像；空值、加载中、失败、离线无缓存或非可信 URL 均完全隐藏头像及其间距，不显示轮廓、首字、品牌图标、骨架、底色圆形或破图标，也不弹错误提示。
- 昵称与头像解耦：`nicknameCustomized=true` 且 `displayName` 非空时展示真实昵称；系统默认昵称、旧数据缺字段或空昵称统一展示“欢迎回来”，端侧禁止按 `新同学_*` 格式猜测。
- 返回账号会话过期时主按钮统一为“短信验证码登录”；说明句保持“登录信息已过期，请用短信验证码重新登录”的完整语法。
- 验证码发送成功后，手机号输入框折叠为“验证码已发送至脱敏号码”和“更换手机号”；验证码态主按钮为“验证并登录”，过期态为“重新获取验证码”。
- 其他方式的可见名称固定为“微信 / QQ / 支付宝 / 其他手机号”，无障碍语义使用“使用微信登录”等完整动作描述，不在可见文案重复“登录”。
- 趣我圈花瓣中心使用明确的两层花蕊；登录页、欢迎页、Android、iOS、Web maskable 图标与 favicon 必须由同一个 `WelcomeAppIconPainter` 生成并通过资产哈希校验，禁止平台图标各自维护。
- Account Area 固定高度：
  - 历史账号态：昵称、脱敏手机号稳定展示；圆形头像仅在成功解码后加入，Account Area 外层高度不变。
  - 本机号码态：大号脱敏手机号、账号创建或恢复说明。
  - 手机号验证码态：手机号输入区、六格验证码区与就近错误提示；主按钮 Y 坐标稳定。
- 验证码必须显示为 6 个独立方框；隐藏输入只能用于焦点、粘贴和键盘控制，普通输入框不得外露。
- 所有异常态必须就近提示，并保留关闭、修改手机号、重试或切换其它方式的清晰路径。手机号格式/验证码不匹配使用字段错误；发送失败、限流、验证码过期使用表单内联卡片；社交失败只在其他登录方式区域展示；同一次失败只允许一个可见反馈。
- 初始能力不可用属于入口选择而非用户错误，静默进入手机号验证码；用户明确点击运营商一键后失败才自动降级并显示无嵌套动作的紧凑 `formInlineCard`，用户开始编辑后清除。
- 背景保持简洁，优先使用系统页面背景；不新增复杂渐变或多余卡片。
- 顶部关闭与帮助按钮触控区不得小于 44dp。
- iPhone 17 为截图基准；iPad/Web 使用同一内容 frame 居中，最大宽度受控，不重排信息层级。
- 所有颜色、间距、字体、文案必须走 `AppColors`、`AppSpacing`、`AppTypography`、`UITextConstants`。

## 状态机

- `resolving`：读取本地摘要并探测运营商能力。
- `returningAccount`：存在可识别账号摘要，且存在立即可执行的会话恢复、手机号重新验证或记住社交授权动作。
- `carrierPhone`：没有可执行返回账号，且运营商探测返回完整可提交能力。
- `phoneOtp`：无历史摘要且运营商不可用，或用户主动点击“其它手机号”。
- `phoneOtpIdle` / `phoneEditing` / `phoneInvalid` / `phoneValid`：手机号输入子状态。
- `sendingCode` / `codeSent` / `codeEditing` / `codeComplete`：发码与验证码输入子状态。
- `loggingIn` / `success` / `codeError` / `codeExpired` / `rateLimited` / `sendFailed` / `loginLocked`：登录与异常子状态。
- `unavailable`：仅表示所有当前可用登录方式都暂不可用；正常情况下必须降级到 `phoneOtp`。
- `submitting`：用户点击主按钮后等待服务端认证。
- `error`：结构化登录错误，可重试或降级。

## 手机号 OTP 不拦截用户契约

- 永远可关闭：关闭登录页必须回安全态，不能回到触发点后再次弹登录。
- 永远可换方式：其它登录方式区域固定可见；倒计时、错误、过期、发送失败时仍可切换方式。
- 永远可修改手机号：除发送中、登录中、成功反馈等瞬时态外，手机号可编辑；编辑手机号后清空验证码和错误。
- 永远有清晰主动作：禁用按钮必须有原因；协议未勾选时点击获取验证码或登录只提示，不发请求。
- 永远不重复提示：手机号、验证码、协议、流程和账号阻断错误各自只在唯一就近承载面展示；协议未勾选也不得额外触发 Toast/Snackbar。
- 永远不自动误登录：短信自动读取只填码，登录仍由用户点击确认。
- 永远不自动发码：returning account 降级到短信登录时只预填手机号，短信发送仍由用户显式点击。

## 登录反馈单通道契约

- `errors.yaml -> RuntimeFailure -> RuntimeRecoveryPolicy -> LoginErrorPresentation -> LoginErrorSurface` 是唯一解释链。
- 同一次失败只允许一个可见反馈；字段错误不进入顶部，社交错误不进入 OTP 小字，账号阻断不降级为普通手机号错误。
- 展示面固定为 `phoneField`、`otpField`、`agreement`、`socialMethod`、`topLevel`、`accountBlocked`；任何新增错误码必须先在 metadata 声明恢复动作，再进入该矩阵。
- `social_provider_cancelled` 由恢复策略吸收，不显示失败。产品支持的平台不得把“未配置、未安装客户端、SDK 缺失、探测超时、平台不支持”合并为一个不可用布尔值：未安装或瞬时探测失败保留入口并就近解释，alpha 未配置保留入口并说明测试环境状态，明确不支持的平台才隐藏；beta/gamma/prod 缺 SDK 或凭据由发布门禁阻断。
- 用户可见文案使用服务端安全 `userMessage`、本地化 codegen baseline 与通用兜底三级链，禁止展示原始异常、debugMessage 或关联 ID。
- 账号暂停、删除、锁定采用稳定阻断面，必须同时提供帮助与关闭安全态。

## 端云契约

- `contracts/metadata/user/user_profile/service.yaml` 新增 `ResolveOneTapLoginHint`，并收敛 `LoginOneTap` / `SendOtp` / `LoginWithPhone` 请求字段。
- `contracts/metadata/user/user_profile/fields.yaml` 新增登录 hint、运营商审计上下文与 consent record 字段。
- `contracts/metadata/user/user_profile/errors.yaml` 新增运营商不可用、token 无效、provider 超时、手机号不匹配、未同意协议、账号暂停/删除等结构化错误。
- `SendOtp` response 必须包含 `maskedPhone`、`expiresInSeconds`、`deliveryStatus`、`requestId`、`challengeId`、`retryAfterSeconds`；验证码只能由服务端 challenge 和短信 provider 持有。
- `LoginWithPhone` request 必须包含 `phone`、`otpCode`、`deviceId`、`platform`、`appVersion`、`agreementVersion`、`privacyVersion`。
- App 不接触真实手机号；真实手机号只在服务端通过 `CarrierGateway` 置换并脱敏落库或返回。

## 四环境验证码策略

- alpha/beta/gamma 默认使用固定测试验证码 `123456`，仍执行 challenge 哈希、有效期、限流、失败次数与一次性消费；禁止任意六位数放通、响应回传验证码或 UI 显示调试码。
- alpha 裸 `flutter run` 的 public plane 必须实现 metadata 同源的 `/v1/auth/otp/send` 与 `/v1/auth/login/phone`，不得返回 HTML 404；独立 alpha runner 使用同一固定码语义。
- beta/gamma 可以显式切换官方沙箱或真实供应商；prod 只允许真实供应商，测试 provider、固定测试码、缺失凭据或缺失密封密钥必须 fail-closed。
- user-service 仅保存 challenge/code hash；短信明文与真实收件号码封装为短时 `codeRef`，integration-service 只在供应商调用前于内存中解析，日志、指标、attempt ledger 与公开响应不得包含手机号、验证码、token、授权载荷或 `codeRef`。
- provider 模式的 user-service → integration-service 请求必须同时使用受 scope 约束的 service principal、HTTPS 与 mTLS 客户端证书；CA、client cert、client key 由 Secret Manager 以文件注入，任一缺失或证书校验失败均 fail-closed。

## 数据与副作用

- 已绑定手机号：更新凭证 `lastUsedAt`、设备 `lastActiveAt`、签发 token 并返回账号摘要。
- 未绑定手机号：创建 `user_profiles`、primary `personas`、`credential_bindings`、`user_devices`、`consent_records`。
- 默认昵称由服务端生成并返回 `nicknameCustomized=false`；头像可为空，App 不生成或显示任何默认头像。
- provider audit 只记录 provider、requestId、latencyMs、resultCode，不记录真实手机号或 carrier token。
- OTP challenge 是验证码真相源；登录成功后一次性消费，验证码错误时不清空 challenge，方便用户修改。
- 短信服务商只记录 requestId、deliveryStatus、failureReason、latencyMs；日志禁止明文手机号和验证码。

## 权限与异常语义

- hint/login one-tap 是 public operation；owner 级账号管理仍必须 required。
- 未勾选协议时本地阻断，不发网络请求。
- 服务端仍需对缺失 `agreementVersion` / `privacyVersion` 返回 `USER.AUTH.consent_required`，防止绕过 App。
- `otp_mismatch` 映射到红框但保留验证码；`otp_expired` 映射到重新获取；`rate_limited` 映射到倒计时；provider 失败映射到可重试 `sendFailed`。
- `account_suspended`、`account_deleted` 必须展示结构化解释和可恢复入口，不得进入默认账号创建。
- SDK 不可用或 provider timeout 必须在 1.2s 内降级，不能长时间 loading。

## 观测、SLO 与灰度

- KPI：登录页曝光到主按钮点击转化率、carrier hint 成功率、LoginOneTap 成功率、新账号创建成功率、登录成功后进入目标态成功率。
- 手机号 OTP KPI：手机号输入转化率、发码点击率、发码成功率、验证码填写完成率、OTP 登录成功率、异常后换方式比例。
- SLO：
  - 登录页首帧 P95 <= 500ms。
  - carrier capability/hint P95 <= 1200ms。
  - SendOtp P95 <= 1200ms。
  - 短信服务商 accepted P95 <= 1500ms。
  - LoginOneTap P95 <= 1500ms。
  - LoginWithPhone P95 <= 1500ms。
  - 登录成功到目标态 P95 <= 2000ms。
  - provider 错误率 <= 2%，超过阈值自动降级。
- 埋点：`login_page_exposed`、`login_state_resolved`、`carrier_hint_requested`、`carrier_hint_resolved`、`login_primary_clicked`、`login_success`、`login_failed`、`login_dismissed`、`login_phone_otp_entered`、`login_otp_request_clicked`、`login_otp_send_succeeded`、`login_otp_send_failed`、`login_otp_code_changed`、`login_phone_login_clicked`、`login_phone_login_succeeded`、`login_phone_login_failed`。
- 登录原始事件明细保留 30 天，聚合指标保留 180 天；聚合指标和错误事件全量，成功明细 alpha/beta/gamma 全量、prod 默认 10%。配置键为 `sys.user.auth.success_detail_sample_ratio`、`sys.user.auth.raw_event_retention_days`、`sys.user.auth.aggregate_metric_retention_days`。
- 当前已落地配置键、环境默认值和登录事件 30 天 TTL，但尚未取得运行时采样 consumer 与 180 天聚合保留执行证据；该缺口继续阻断商业准入。
- 仪表盘真相源为 `quwoquan_ops/observability/monitoring/dashboards/l2_auth_login_commercial.json`；provider 非 2xx 比率连续两个 5 分钟窗口超过 2%，或登录 P95 连续两个窗口超过对应 metadata SLO 时告警，并要求验证 provider 降级、短信恢复入口与配置回滚。
- 灰度：新登录页、新 hint endpoint、provider vendor 均可按 appVersion、platform、渠道和用户桶控制；回滚到“运营商不可用 + 后续登录方式入口”。

## 验收标准

- A1：历史账号摘要存在时，登录页稳定展示合规昵称与脱敏手机号；真实头像仅在成功解码后显示，点击主按钮必须请求服务端刷新 token。
- A2：运营商返回未注册本机号码时，登录页展示号码态，点击主按钮创建默认账号和主分身。
- A3：没有历史摘要且运营商不可用，或用户点击“其它手机号”，登录页进入手机号 OTP 态，不出现占位 toast。
- A4：手机号 OTP 12 个高保画面和所有异常逃生路径都有 local_contract 覆盖。
- A5：未勾选协议不发码、不登录；服务端缺协议版本返回 `consent_required`。
- A6：端云契约由 metadata 生成，Dart DTO、Go handler/service、测试 fixture 对齐。
- A7：数据库副作用、consent 留痕、短信 provider audit 和错误结构化均有 api_integration 证据。
- A8：iPhone 17、iPad、Web 截图证据覆盖高保和响应式。
- A9：同一错误不同时出现 Toast/Snackbar 与内联提示；所有 USER.AUTH 错误均命中唯一 `LoginErrorSurface`。
- A10：验证码填满及 returning 手机号预填均不自动提交网络请求。
- A11：登录文案、头像成功才显示、昵称来源标记、两层花蕊和全平台图标通过 local_contract、视觉基线与确定性哈希校验；Web 不得回退 Flutter 默认图标。
- A12：空账号摘要不会出现返回账号卡或“一键登录”；返回会话显示“继续登录”，运营商才显示“本机号码一键登录”。
- A13：运营商显式失败降级后只有“获取验证码”一个主动作；发码成功折叠手机号并显示“验证并登录”和“更换手机号”。
