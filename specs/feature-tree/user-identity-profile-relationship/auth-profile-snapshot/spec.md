# L2 Business Capability：认证资料快照 (`auth-profile-snapshot`)

> 所属领域：[`user-identity-profile-relationship`](../spec.md)
>
> 设计归属：[L1 DEC-001](../design.md#dec-001)

## 1. 能力目标

提供认证、refresh token、owner/Persona 资料快照与凭证管理，使登录主体在刷新、切换和资料更新后保持一致且安全。

## 2. 范围与非目标

### In Scope

- OTP/手机号登录、一键登录、匿名登录、refresh token、logout
- owner 级凭证列表、绑定/解绑、最后一个凭证保护
- ownerId / activeSub / accountState / identityOrigin 等登录结果快照一致性

### Out of Scope

- 账号注销、恢复申诉、数据导出
- Web 宽屏登录门 UI 细节

## 3. Journey / Scenario 贡献

- [`JNY-001 / SCN-004`](../../spec.md#scn-004)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：认证、refresh token、owner/subAccount 快照与凭证管理的能力级 SIT 验收，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。

## 4. Story



- [`auth-token-lifecycle`](./auth-token-lifecycle/spec.md)：定义“认证 Token 生命周期”的可观察主路径、失败语义及父能力交接。
- [`profile-read-update`](./profile-read-update/spec.md)：读取与更新资料时保持公开字段、私有凭证和聊天快照边界一致。
- [`profile-snapshot-versioning`](./profile-snapshot-versioning/spec.md)：定义“资料快照版本控制”的可观察主路径、失败语义及父能力交接。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 登录结果快照、凭证管理与会话状态机端云一致

- LoginWithPhone / LoginOneTap / LoginAnonymous / RefreshToken / Logout 的 request/response 字段与 metadata、App DTO、服务端行为一致。
- accessToken、refreshToken、ownerId、activeSub、accountState、identityOrigin 在 App Session 与服务端 contract 中同源。
- ListCredentials / BindCredential / UnbindCredential 的鉴权模式、错误码与“最后一个凭证禁止解绑”约束可验证。
- 正常冷启动在安全启动面可见后恢复既有会话；没有有效会话时以安装身份单飞调用 LoginAnonymous，并只把服务端签发的 bearer principal 用作游客业务主体。
- 可信匿名会话不得把游客呈现为显式登录用户，不得覆盖并发完成的正式登录；离线或服务暂不可用时业务请求获得 canonical 可重试失败，不得退回裸设备 actor header 或空列表伪成功。

<a id="req-002"></a>
### REQ-002 负责资料读取、资料更新提案、会话刷新、设备 token、恢复与安全风控的统一边界

- 负责资料读取、资料更新提案、会话刷新、设备 token、恢复与安全风控的统一边界。
- 预留第三方授权票据与 passkey challenge/assertion 的统一认证边界，确保 App 只透传短期票据或 WebAuthn 结果，不在客户端持有高价值密钥。
- 跨边界字段、operation 与错误语义只引用所属服务 contracts；本节点不得复制 wire 定义。
- `SubAccount` 快照必须可独立装配，不能把其他子账号的私有资料、关系与上下文混入当前会话。
- 登录刷新、设备注册、提案确认/应用/拒绝、恢复与锁定必须具备幂等、版本控制和回滚语义。
- 微信 / Apple / passkey 登录都必须遵守“App 只传短期凭据，服务端负责换取长期会话”的原则；任何 provider secret、WebAuthn 验签私密逻辑不得落在客户端。
- 电话号码、第三方 union 标识、设备指纹、风险字段与审计字段必须严格按 metadata 分级与屏蔽。
- 风控锁定、异常登录、恢复发起与设备变更必须可审计。
- passkey / 第三方登录入口未开通时必须降级清晰，不得破坏手机号 OTP 与 refresh 主路径。
- 恢复链路与登录链路必须支持灰度与回滚，不可影响正常登录主路径。

## 6. 契约与依赖

- 上游能力：[`user-identity-profile-relationship`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 登录结果快照、凭证管理与会话状态机端云一致

- GIVEN 执行“登录结果快照、凭证管理与会话状态机端云一致”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“登录结果快照、凭证管理与会话状态机端云一致”对应动作。
- THEN LoginWithPhone / LoginOneTap / LoginAnonymous / RefreshToken / Logout 的 request/response 字段与 metadata、App DTO、服务端行为一致。
- THEN accessToken、refreshToken、ownerId、activeSub、accountState、identityOrigin 在 App Session 与服务端 contract 中同源。
- THEN ListCredentials / BindCredential / UnbindCredential 的鉴权模式、错误码与“最后一个凭证禁止解绑”约束可验证。
- THEN 首次启动、既有匿名会话恢复和并发业务请求只产生一个 LoginAnonymous bootstrap，后续请求由 bearer principal 提供 Persona 业务主体，而 UI 仍保持游客语义。
- THEN bootstrap 失败可重试且不阻塞安全启动面；正式登录一旦开始或完成，迟到的匿名结果不得覆盖正式会话与返回账号凭证。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 登录结果快照、凭证管理与会话状态机端云一致

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：LoginWithPhone / LoginOneTap / LoginAnonymous / RefreshToken / Logout 的 request/response 字段与 metadata、App DTO、服务端行为一致。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效
