# L3 Story：commercial-login-entry--one-tap-and-phone-otp

## 功能说明

本 Story 将登录页收敛为同一商用登录骨架下的三类入口：历史账号一键登录、本机号码一键登录/创建、其它手机号验证码登录。登录页以高保图为唯一体验目标，移动端、iPad 与 Web 共用同一视觉骨架；差异只允许出现在 Account Area，不能维护第二套登录页面或未上线兼容分支。

## 用户价值

- 老用户在换机、会话过期或手动退出后，可以看到自己熟悉的头像、昵称与脱敏手机号，并通过服务端二次校验快速回到目标态。
- 新用户在运营商网关可用时，可以用本机号码一键创建默认账号、默认头像昵称与主分身，随后在“我的主页”完善资料。
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

- 不实现微信、QQ、支付宝、Apple、Passkey 的正式 SDK 登录。
- 不保留未上线旧聚合登录 request 字段、旧 `/v1/auth/login` 别名路由或第二套 Web 登录视觉。
- Web 不承诺运营商一键登录可用；Web 仅展示同构壳并按能力位降级。

## UX 与视觉约束

- 三入口同构：Logo、品牌、主标题、副标题、主按钮、协议区、其他登录方式位置和高度一致。
- Account Area 固定高度：
  - 历史账号态：圆形头像、昵称、脱敏手机号。
  - 本机号码态：大号脱敏手机号、账号创建或恢复说明。
  - 手机号验证码态：手机号输入区、六格验证码区与就近错误提示；主按钮 Y 坐标稳定。
- 验证码必须显示为 6 个独立方框；隐藏输入只能用于焦点、粘贴和键盘控制，普通输入框不得外露。
- 所有异常态必须就近提示，并保留关闭、修改手机号、重试或切换其它方式的清晰路径。
- 背景保持简洁，优先使用系统页面背景；不新增复杂渐变或多余卡片。
- 顶部关闭与帮助按钮触控区不得小于 44dp。
- iPhone 17 为截图基准；iPad/Web 使用同一内容 frame 居中，最大宽度受控，不重排信息层级。
- 所有颜色、间距、字体、文案必须走 `AppColors`、`AppSpacing`、`AppTypography`、`UITextConstants`。

## 状态机

- `resolving`：读取本地摘要并探测运营商能力。
- `returningAccount`：存在历史账号摘要，或运营商 hint 返回已绑定账号摘要。
- `carrierPhone`：无历史摘要且运营商 hint 返回未注册本机号码。
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
- 永远不大弹窗阻断：错误在手机号输入区或验证码区就近展示，Toast 只用于协议未勾选等轻提示。
- 永远不自动误登录：短信自动读取只填码，登录仍由用户点击确认。

## 端云契约

- `contracts/metadata/user/user_profile/service.yaml` 新增 `ResolveOneTapLoginHint`，并收敛 `LoginOneTap` / `SendOtp` / `LoginWithPhone` 请求字段。
- `contracts/metadata/user/user_profile/fields.yaml` 新增登录 hint、运营商审计上下文与 consent record 字段。
- `contracts/metadata/user/user_profile/errors.yaml` 新增运营商不可用、token 无效、provider 超时、手机号不匹配、未同意协议、账号暂停/删除等结构化错误。
- `SendOtp` response 必须包含 `maskedPhone`、`expiresInSeconds`、`deliveryStatus`、`requestId`、`challengeId`、`retryAfterSeconds`、`debugCode`，以驱动已发送、频控、服务商失败和调试联调状态。
- `LoginWithPhone` request 必须包含 `phone`、`otpCode`、`deviceId`、`platform`、`appVersion`、`agreementVersion`、`privacyVersion`。
- App 不接触真实手机号；真实手机号只在服务端通过 `CarrierGateway` 置换并脱敏落库或返回。

## 数据与副作用

- 已绑定手机号：更新凭证 `lastUsedAt`、设备 `lastActiveAt`、签发 token 并返回账号摘要。
- 未绑定手机号：创建 `user_profiles`、primary `personas`、`credential_bindings`、`user_devices`、`consent_records`。
- 默认昵称由服务端生成，默认头像来自受控头像池或为空，由 App 默认头像组件兜底。
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
- 灰度：新登录页、新 hint endpoint、provider vendor 均可按 appVersion、platform、渠道和用户桶控制；回滚到“运营商不可用 + 后续登录方式入口”。

## 验收标准

- A1：历史账号摘要存在时，登录页展示头像、昵称、脱敏手机号，点击主按钮必须请求服务端刷新 token。
- A2：运营商返回未注册本机号码时，登录页展示号码态，点击主按钮创建默认账号和主分身。
- A3：没有历史摘要且运营商不可用，或用户点击“其它手机号”，登录页进入手机号 OTP 态，不出现占位 toast。
- A4：手机号 OTP 12 个高保画面和所有异常逃生路径都有 local_contract 覆盖。
- A5：未勾选协议不发码、不登录；服务端缺协议版本返回 `consent_required`。
- A6：端云契约由 metadata 生成，Dart DTO、Go handler/service、测试 fixture 对齐。
- A7：数据库副作用、consent 留痕、短信 provider audit 和错误结构化均有 api_integration 证据。
- A8：iPhone 17、iPad、Web 截图证据覆盖高保和响应式。
