# L2 设计：onboarding-and-identity-entry

## 设计目标

本能力用一个登录页面、一套结构化错误契约和一个环境装配入口承载手机号 OTP、三网本机号认证、微信、支付宝与 QQ 登录。任何失败都必须让用户知道发生了什么、接下来能做什么，并且不会出现重复提示、自动提交、失效入口或关闭后再次弹登录。

## 单一反馈链

```text
errors.yaml
  -> RuntimeErrorResponse / CloudException / RuntimeFailure
  -> RuntimeRecoveryPolicy
  -> LoginErrorPresentation
  -> LoginErrorSurface
  -> LoginPage 单一展示位置
```

- `errors.yaml` 是稳定错误码、双语 baseline、`recovery.action`、`disruptionLevel` 与 `afterSeconds` 的唯一真相源。
- `LoginErrorPresentation` 是登录页唯一反馈模型；页面不得另建错误码 switch、直接展示异常字符串或同时触发 Toast/Snackbar。
- `LoginErrorSurface` 只决定“在哪里显示”，不重新解释错误：
  - `phoneField`：手机号格式。
  - `otpField`：验证码错误、过期、发送失败、频控。
  - `agreement`：协议未同意。
  - `socialMethod`：微信、支付宝、QQ 授权失败或不可用。
  - `topLevel`：运营商、网络、会话等流程失败。
  - `accountBlocked`：账号暂停、删除、锁定等阻断态。
- 同一次失败只允许一个可见承载面。`social_provider_cancelled` 为 `absorb + silent`，恢复原状态且不显示错误。
- 用户可见文案不得包含 `debugMessage`、provider 原始响应、authCode、token、secret、URL query、requestId 或 traceId；关联标识只进入结构化观测。

## OTP 状态与提交

- 手机号编辑、验证码编辑、异步活动和反馈相互独立，输入中不构成错误。
- 系统短信自动填充只写入 6 位验证码，不自动登录；登录必须由用户显式点击。
- returning account 的短信降级只预填手机号，不自动发码；发码必须由用户显式点击。
- 重发失败时保留已送达 challenge、手机号与验证码，避免把用户从可继续状态退回起点。
- 每次异步尝试带单调 attempt id；过期结果不得覆盖新状态，重复点击在活动期间被抑制。

## 登录能力与平台防腐

- UI 只消费 `PlatformCapabilities`，不判断 Android/iOS/Web。
- `NativeAuthBridge` 统一承载微信、支付宝、QQ SDK 授权；`OneTapLoginClient` 统一承载三网 capability probe 与本机号 token。
- 能力已知不可用时不展示入口；能力运行时失败时在原位置给出重试或切换方式，不能保留可点击死入口。
- 原生桥只返回短期 authCode/carrier token，服务端完成身份置换；App 不持久化厂商 secret、真实本机号或长期 provider token。

## 四环境装配

- alpha：确定性本地 fixture 只用于 local_contract，不进入运行时认证链路。
- beta/gamma/prod：真实 user-service 与部署注入的外部 provider；凭据或平台能力缺失时 fail-closed。
- prod：真实厂商与真实运营商；缺配置时隐藏入口或返回结构化 unavailable，绝不 mock 成功。
- 所有环境共享同一 DTO、错误码、页面状态机与观测字段，不维护环境专属业务分支。

## AuthContinuation 与退出

- 关闭登录页先清理 pending continuation，再进入不会重新触发登录门的安全态。
- 登录成功不提前清理 continuation；由目标表面原子消费并清理。
- 所有强登录入口声明 `allowGuestDismissPop: false`；内部 tab 目标用 continuation，不以路由字符串猜测。

## 可观测与安全

- 记录 `code`、`operationId`、`surfaceId`、`recoveryAction`、`disruptionLevel`、`requestId`、`traceId`、provider、耗时与结果；不记录可见 message 或凭证。
- user-service 客户端错误响应默认不含 debug；外部 provider 错误必须脱敏后再进入日志或 RuntimeErrorResponse。
- SLO：capability probe/hint P95 ≤ 1200ms，票据置换 P95 ≤ 1500ms，登录成功到目标态 P95 ≤ 2000ms。

## 回滚

- 单 provider 可由能力开关下线，页面自动收敛到剩余方式。
- 运营商链路异常时降级手机号 OTP，不得回退到 dev token。
- 服务端缺凭证、签名失败或上游异常一律 fail-closed；回滚不允许启用 mock、debugCode 或客户端 secret。
