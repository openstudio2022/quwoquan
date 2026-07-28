# L3 Story：引导同意流程 (`onboarding-consent-flow`)

> 所属能力：[`onboarding-and-identity-entry`](../spec.md)

> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为管理身份、Persona 或关系的用户，
我希望手机号登录与一键登录共享同一勾选语义、协议文案、版本真相源，不存在第二套硬编码版本号，
从而安全地维持身份、画像与关系状态。

## 2. 范围与非目标

### In Scope

- “引导同意流程”的输入、可观察主路径、失败语义以及与父能力的交接。
- 登录动作在协议未确认时弹出统一确认 sheet；确认后恢复且只恢复一次原待执行动作。
- agreementVersion/privacyVersion 与 AuthLegalConfig 真相源一致。
- one-tap 登录请求必须透传协议版本，后端能够消费并留痕。
- 法律正文 URL 可达性与外部法务发布流程。
- 数据导出、账号注销、撤回同意的后续权利动作。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 引导同意流程

- “引导同意流程”必须通过父能力公开契约交付可观察结果；失败时返回 canonical failure，不写入成功事实。

<a id="req-002"></a>
### REQ-002 服务本地契约引用边界

- 跨边界字段、operation 与错误语义只引用所属服务 contracts；本节点不得复制 wire 定义。

<a id="req-003"></a>
### REQ-003 未勾选协议不得登录，协议版本需进入登录契约

- 手机号登录与一键登录共享同一勾选语义、协议文案、版本真相源，不存在第二套硬编码版本号。
- 协议未确认时页面不显示红色协议错误；sheet 使用“请先阅读并同意相关协议 / 同意后即可继续登录 / 同意并继续 / 暂不”。
- 一键、手机号和社交登录均携带同一 `AuthLegalConfig` 版本；社交后续绑定手机号不重复展示协议，但最终完成操作仍校验已接受版本。

## 4. 契约引用

- canonical：`quwoquan_app/lib/ui/user/pages/login_page.dart`
- canonical：`quwoquan_app/lib/core/auth/auth_legal_config.dart`
- canonical：`quwoquan_service/services/user-service/contracts/account/account_session/operations.yaml`
- canonical：`quwoquan_service/services/user-service/contracts/account/credential_binding/operations.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 引导同意流程

- GIVEN 管理身份、Persona 或关系的用户具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“引导同意流程”对应的公开行为。
- THEN 通过父能力公开契约交付“引导同意流程”的可观察结果。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

<a id="gwt-002"></a>
### GWT-002 未勾选协议不得登录，协议版本需进入登录契约

- GIVEN 用户选择手机号或一键登录。
- WHEN 用户未勾选协议，或勾选后提交登录。
- THEN 未确认时弹出统一 sheet 且不发起请求；“同意并继续”只恢复一次原动作，提交时使用同一 AuthLegalConfig 的协议版本并由服务端留痕。

## 6. 依赖

- 前置要求：[`onboarding-and-identity-entry`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 引导同意流程 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺少能够证明“引导同意流程”已满足当前规格的真实测试证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-002"></a>
### OPEN-002 未勾选协议不得登录，协议版本需进入登录契约

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：手机号登录与一键登录共享同一勾选语义、协议文案、版本真相源，不存在第二套硬编码版本号。
- 完成判定：`GWT-002` 对应行为满足且真实测试 `spec_ref` 有效。
