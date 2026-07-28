# L2 Business Capability：引导与身份入口 (`onboarding-and-identity-entry`)

> 所属领域：[`user-identity-profile-relationship`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

负责从欢迎页、冷启动、未登录入口、登录中断恢复到登录后落点的完整身份进入链路。

## 2. 范围与非目标

### In Scope

- 由本目录 Story 组合交付“onboarding-and-identity-entry”的独立业务结果。

### Out of Scope

- 其他 L2 的事实所有权、metadata schema 与实现施工步骤。

## 3. Journey / Scenario 贡献

- [`JNY-001 / SCN-004`](../../spec.md#scn-004)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：负责从欢迎页、冷启动、未登录入口、登录中断恢复到登录后落点的完整身份进入链路，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。

## 4. Story



- [`four-environment-commercial-login-maturity`](./four-environment-commercial-login-maturity/spec.md)：application contract 覆盖 provider 失败、正常排队和错误验证码拒绝。
- [`onboarding-consent-flow`](./onboarding-consent-flow/spec.md)：定义“引导同意流程”的可观察主路径、失败语义及父能力交接。
- [`post-login-landing`](./post-login-landing/spec.md)：定义“内容登录落点”的可观察主路径、失败语义及父能力交接。
- [`two-state-one-tap-login-commercial-login-entry`](./two-state-one-tap-login-commercial-login-entry/spec.md)：本机号码首次登录在服务端完成账号、persona、credential、device 与 consent 持久化。
- [`welcome-entry-routing`](./welcome-entry-routing/spec.md)：定义“欢迎入口路由”的可观察主路径、失败语义及父能力交接。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 onboarding and identity entry 能力 SIT

- 本能力必须组合直属 Story 与公开契约，交付“负责从欢迎页、冷启动、未登录入口、登录中断恢复到登录后落点的完整身份进入链路”所定义的业务结果；失败终态必须可区分且不得伪造成功。
- 微信 / 支付宝 / QQ 原生登录入口、三网本机号一键入口、系统凭据入口的显隐和降级由 PlatformCapabilities 驱动，不依赖 UI 层平台判断。
- Android `Credential Manager` 与 iOS `AuthenticationServices / Password AutoFill` 的客户端接口与产品语义已预留，未开通时统一降级到手机号 OTP。

<a id="req-002"></a>
### REQ-002 支持手机号验证码、三网本机号一键、微信、支付宝和 QQ 并行登录，并统一归入 `OwnerAccount` 创建或恢复流程

- 支持手机号验证码、三网本机号一键、微信、支付宝和 QQ 并行登录，并统一归入 `OwnerAccount` 创建或恢复流程。
- 微信 / 支付宝 / QQ 原生授权入口、三网本机号一键与手机号 OTP 的统一收口。
- 跨边界字段、operation 与错误语义只引用所属服务 contracts；本节点不得复制 wire 定义。
- 欢迎页是身份入口，不只是品牌 splash；必须知道“未登录 / 已登录 / 登录失效 / 多子账号待选择”四种状态。
- 手机号验证码、三网本机号一键、微信、支付宝、QQ 必须是并行入口，而不是单一路径的补充按钮。
- `Credential Manager` / `AuthenticationServices` / 微信 OpenSDK 等平台差异必须收口到 `PlatformCapabilities + NativeBridge`，UI 不得直接调用原生 SDK。
- App 侧只记住登录方式、掩码账号与可续期会话凭据；明文密码、第三方密钥、WebAuthn 私钥不得落盘到业务层。
- 登录成功后不能直接把 `OwnerAccount` 暴露给应用世界；必须进入某个具体 `SubAccount` 上下文。
- 仅有一个 `SubAccount` 时，默认自动进入该子账号；拥有多个 `SubAccount` 时，必须支持安全、显式、可恢复的选择或新建。
- 登录入口必须清晰解释当前启用方式的差异、失败后的兜底与恢复路径。
- 一键登录固定展示推荐主动作“本机号码一键登录”和同宽次动作“其他手机号登录”；手机号入口不得重复出现在第三方 footer。
- 微信、QQ、支付宝三个入口在所有自有登录步骤使用同一 footer 槽位和垂直基线；不可用能力保留槽位并给出具象不可用语义。
- 社交首登需要手机号时，完成手机号 OTP 与凭证绑定前不得签发可进入应用的会话，也不得消费登录成功 continuation。

## 6. 契约与依赖

- 上游能力：[`user-identity-profile-relationship`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 onboarding and identity entry 能力 SIT

- GIVEN 执行“onboarding and identity entry 能力”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“onboarding and identity entry 能力”对应动作。
- THEN 直属 Story 共同交付“负责从欢迎页、冷启动、未登录入口、登录中断恢复到登录后落点的完整身份进入链路”，失败终态可区分且不产生伪成功事实。
- THEN 微信 / 支付宝 / QQ 原生登录入口、三网本机号一键入口、系统凭据入口的显隐和降级由 PlatformCapabilities 驱动，不依赖 UI 层平台判断。
- THEN Android `Credential Manager` 与 iOS `AuthenticationServices / Password AutoFill` 的客户端接口与产品语义已预留，未开通时统一降级到手机号 OTP。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 商用登录正式凭据与受控 SDK 尚未注入发布密钥系统

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：仓库已经具备 fail-closed provider 契约与客户端入口，但微信、QQ、支付宝和三网本机号的生产凭据、受控 SDK 与供应商后台仍需外部主体开通；本地协议测试不能替代真实登录。
- 完成判定：生产发布密钥系统注入四类正式 provider 凭据与受控 SDK，`prod-hosted` 真实网络真机完成登录、首登资料同步、失败恢复与回滚验证，并由 [`four-environment-commercial-login-maturity`](./four-environment-commercial-login-maturity/spec.md#gwt-001) 的直接 `spec_ref` 留证。
- 依赖：微信/QQ/支付宝/运营商开发者主体、生产应用配置、受控 SDK、签名包与真机测试账号。

<a id="open-002"></a>
### OPEN-002 onboarding and identity entry 能力 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：负责从欢迎页、冷启动、未登录入口、登录中断恢复到登录后落点的完整身份进入链路。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效
