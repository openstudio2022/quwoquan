# L2 Design：引导与身份入口 (`onboarding-and-identity-entry`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“负责从欢迎页、冷启动、未登录入口、登录中断恢复到登录后落点的完整身份进入链路”需要 `four-environment-commercial-login-maturity`、`onboarding-consent-flow`、`post-login-landing`、`two-state-one-tap-login-commercial-login-entry`、`welcome-entry-routing` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：负责从欢迎页、冷启动、未登录入口、登录中断恢复到登录后落点的完整身份进入链路。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`four-environment-commercial-login-maturity`](./four-environment-commercial-login-maturity/spec.md)：application contract 覆盖 provider 失败、正常排队和错误验证码拒绝。
- [`onboarding-consent-flow`](./onboarding-consent-flow/spec.md)：定义“引导同意流程”的可观察主路径、失败语义及父能力交接。
- [`post-login-landing`](./post-login-landing/spec.md)：定义“内容登录落点”的可观察主路径、失败语义及父能力交接。
- [`two-state-one-tap-login-commercial-login-entry`](./two-state-one-tap-login-commercial-login-entry/spec.md)：本机号码首次登录在服务端完成账号、persona、credential、device 与 consent 持久化。
- [`welcome-entry-routing`](./welcome-entry-routing/spec.md)：定义“欢迎入口路由”的可观察主路径、失败语义及父能力交接。

## 3. 端云与数据流

- 上游能力：[`user-identity-profile-relationship`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 登录方式共用页面骨架、结构化错误与环境装配
- 决策：登录方式共用页面骨架、结构化错误与环境装配。
- 理由：负责从欢迎页、冷启动、未登录入口、登录中断恢复到登录后落点的完整身份进入链路。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 影响 Story：[`four-environment-commercial-login-maturity`](./four-environment-commercial-login-maturity/spec.md)、[`onboarding-consent-flow`](./onboarding-consent-flow/spec.md)、[`post-login-landing`](./post-login-landing/spec.md)、[`two-state-one-tap-login-commercial-login-entry`](./two-state-one-tap-login-commercial-login-entry/spec.md)、[`welcome-entry-routing`](./welcome-entry-routing/spec.md)
- 关联验收：`SIT-001`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 用户可见文案不得包含 `debugMessage`、provider 原始响应、authCode、token、secret、URL query、requestId 或 traceId；关联标识只进入结构化观测。
- prod：真实厂商与真实运营商；缺配置时隐藏入口或返回结构化 unavailable，绝不 mock 成功。
- 关闭登录页先清理 pending continuation，再进入不会重新触发登录门的安全态。
