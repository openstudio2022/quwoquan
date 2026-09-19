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

<a id="dec-002"></a>
### DEC-002 登录流程由单一正交状态 owner 驱动
- 决策：`LoginFlowController` 是 `/login` 内部步骤、异步 operation、协议确认、OTP challenge、反馈与 terminal callback 的唯一状态 owner；页面只渲染不可变状态并发送用户意图。
- 理由：将页面步骤与 loading/error 混入组合枚举会产生不可退出状态、重复回写和布局漂移。
- 被否决方案：每个登录方式维护独立页面、Timer、提交态和错误卡，或继续扩充组合 OTP phase。
- 约束与影响：所有步骤共享顶部导航、可滚动正文与固定第三方登录 footer；ready、失败、取消、迟到回调和返回只允许经过 controller 状态迁移。
- 关联要求：`REQ-001`、`REQ-002`
- 影响 Story：[`onboarding-consent-flow`](./onboarding-consent-flow/spec.md)、[`post-login-landing`](./post-login-landing/spec.md)、[`two-state-one-tap-login-commercial-login-entry`](./two-state-one-tap-login-commercial-login-entry/spec.md)、[`welcome-entry-routing`](./welcome-entry-routing/spec.md)
- 关联验收：`SIT-001`

<a id="dec-003"></a>
### DEC-003 社交首登绑定手机号先于会话签发
- 决策：社交票据置换只返回“已认证会话”或“需要绑定手机号”的单轨判别结果；首次身份需要绑定时只签发短期、一次性 binding ticket，完成手机号 OTP 与凭证唯一性校验后才原子签发 `AuthSessionGrant`。
- 理由：先签发完整 session、再由页面补绑手机号会允许关闭页面或进程恢复绕过门禁。
- 被否决方案：复用登录后 bearer `BindPhoneCredential`、由 App 暂存完整 session、或以本地布尔值表示绑定完成。
- 约束与影响：binding ticket 不得进入日志或分析事件；过期、冲突、重复消费均返回 canonical error，失败不得产生可进入应用的 session。
- 关联要求：`REQ-002`
- 影响 Story：[`four-environment-commercial-login-maturity`](./four-environment-commercial-login-maturity/spec.md)、[`post-login-landing`](./post-login-landing/spec.md)、[`two-state-one-tap-login-commercial-login-entry`](./two-state-one-tap-login-commercial-login-entry/spec.md)
- 关联验收：`SIT-001`

<a id="dec-004"></a>
### DEC-004 Alpha 合成登录采用非电话本地 typed 边界

- 决策：AccountSession / AuthenticationChallenge 保留真实 HTTP 登录与短信合同不变；在对象 canonical `quwoquan_service/services/user-service/contracts/account/authentication_challenge/fields.yaml` 声明本地演练输入/结果值类型。当前生成器尚无本地入口投影时只冻结值合同与接缝，不手写 DTO、不注册假 HTTP operation，也不突破 HTTP 对象禁止 runtime_entrypoints 的门禁。
- 理由：非认证演练标识不能占用真实手机号语义；公开演练提示不能降低真实 OTP/凭据保密级别。线上页面不依赖 Alpha 实现，组合根用 capability 选择本地流程意图或 Remote 登录意图，controller 共享步骤/取消/错误状态但不复用 phone/otpCode 数据槽。
- 最小接缝：普通手写 application/public 接口 `SyntheticChallengePort.begin(BeginSyntheticChallenge)` 与 `SyntheticSessionPort.complete(CompleteSyntheticChallenge)` 只引用同源生成的值类型/失败类型；前者返回 `SyntheticChallengeView`，后者返回 `SyntheticSessionResult`，失败使用生成的 `SyntheticLoginFailure`。接口不要求 metadata 生成，不新增本地端口协议或 operation registry。仅从所属对象 fields 的显式端侧导出根递归生成参数、结果与严格 validator；未正式生成前不宣称 Dart 类型可导入。
- 信任前置：端口只在已消费 `VerifiedRehearsalSpace.isIsolated=true` 且三存储同 binding 隔离后装配；请求不携带自报 source/空间授权。空间及 namespace 引用 runtime-config DEC-007；普通 default、在线 source 与未水合拒绝装配，不读旧空间后再判断，不复制授权台账。
- 标识与确认语义：canonical 值类型冻结专用非电话语法；随机后缀由本地能力生成，不从手机号/邮箱/姓名派生。identity 在 source/snapshot/instance 内唯一。展示端 SyntheticChallengeView 与证据端 SyntheticLoginEvidence 的演练提示保持固定非认证 UI 确认；CompleteSyntheticChallenge 的同名字段为受限用户提交值，机器约束只允许 canonical account_session 字段声明的 ASCII 格式和长度，合法错误输入必须能进入端口比较，不能用展示 const 拦掉业务失败计数。格式之外的自由文本/PII/超长/Unicode先拒绝且不得记录。端口按当前challenge实际提示比较，错提示和错identity在同一事务累计尝试次数，同request幂等重放不重复计数；不能只测试错label代替错提示锁定。提交值不新增公开证据授权，展示/证据端固定值不放宽。该流程不是秘密、不是 OTP，不向 SMS/AutoFill 或真实登录接口发送。
- 一致性：begin 的 request identity 同 payload 重放返回同一未失效 challenge，不同 payload 冲突；complete 成功将挑战消费、本地身份及幂等结果原子提交。失败无 session；相同 request 成功响应丢失可回读同结果，其他重复消费拒绝。有效期最多 300 秒，错提示最多 5 次锁定；过期与空间变化拒绝而不删除其他空间。持久身份使用独立随机 ID，不恢复 canonical creator。
- 失败恢复：本地闭集失败 `unavailable / invalidInput / expired / mismatch / attemptsExceeded / conflict / storageUnavailable` 只映射所属生成的 typed result；本地业务失败不新增伪 HTTP 错误码。错误文案走既有 l10n owner，不输出原始输入/异常；storageUnavailable 保留已提交状态并由用户重试，无法证明提交状态不得显示成功。
- 隐私：默认所有请求/结果日志 drop。仅单独的受限证据值可在 isolated Alpha 经完整语法及字段闭集校验后进入私有测试 plan/截图/native 活动产物；真实 phone/OTP/token、内部 account/persona/challenge/request identity、自由文本和未知字段均不进入此投影。字段 PUBLIC 只表示该合成值不是 PII/认证秘密，不是全局日志豁免；收集器未有隔离作用域和防混入保证时 native 输入/截图仍阻断。
- 观测与回滚：仅记录固定失败类别/成功计数，不记录标识、challenge、提示或 payload；本地不签发服务 SLO/Provider ready。撤销 isolated 资格时停止本地端口装配，不迁移/删除旧 active 或空间；恢复与设备授权仍由现役控制面处理。
- 被否决方案：数字假手机号、固定万能 OTP、真实 SendOtp 透传合成值、HTTP stub 凑生成、手写 DTO、依据日志回显或 runner 字段自证身份/空间。
- 关联要求/验收：本 L2 REQ-001/REQ-002、SIT-001；Story REQ-013/GWT-013。影响 Story：`four-environment-commercial-login-maturity`。值合同测试只证明 schema/分类与在线合同未变，尚缺端口生成/三存储/native 链证据时保留 Story OPEN-004 与 runtime OPEN-021。

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 用户可见文案不得包含 `debugMessage`、provider 原始响应、authCode、token、secret、URL query、requestId 或 traceId；关联标识只进入结构化观测。
- prod：真实厂商与真实运营商；缺配置时隐藏入口或返回结构化 unavailable，绝不 mock 成功。
- 关闭登录页先清理 pending continuation，再进入不会重新触发登录门的安全态。
- 登录观测区分产品漏斗与运维诊断；不得逐秒记录 OTP 倒计时，不得记录手机号、验证码、provider ticket、binding ticket 或 token。
