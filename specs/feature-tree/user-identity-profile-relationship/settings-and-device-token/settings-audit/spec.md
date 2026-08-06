# L3 Story：设置审计 (`settings-audit`)

> 所属能力：[`settings-and-device-token`](../spec.md)

> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为管理身份、Persona 或关系的用户，
我希望系统必须设置域中账号、通知、隐私、外观与分身入口的登录鉴权与审计验收，且失败时不得写入成功事实，
从而安全地维持身份、画像与关系状态。

## 2. 范围与非目标

### In Scope

- “设置审计”的输入、可观察主路径、失败语义以及与父能力的交接。
- Get/UpdateNotificationSettings、Get/UpdatePrivacySettings、Get/UpdateAppearanceSettings、Get/UpdateCallSettings 的 owner 级鉴权。
- 设置页“账号与分身”入口、外观与字号、隐私设置的真实取数与回写。
- settings 页不得继续用 public API 假装 owner 私有数据。
- 账号注销、恢复申诉、数据导出等尚未实现的设置项 UI。
- 推送 token 注册与设备审计页。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 设置审计

- “设置审计”必须通过父能力公开契约交付可观察结果；失败时返回 canonical failure，不写入成功事实。

<a id="req-002"></a>
### REQ-002 服务本地契约引用边界

- 跨边界字段、operation 与错误语义只引用所属服务 contracts；本节点不得复制 wire 定义。

<a id="req-003"></a>
### REQ-003 设置域中账号、通知、隐私、外观与分身入口的登录鉴权与审计验收，且失败时不得写入成功事实

- 系统必须设置域中账号、通知、隐私、外观与分身入口的登录鉴权与审计验收，且失败时不得写入成功事实。

## 4. 契约引用

- canonical：`quwoquan_service/services/user-service/contracts/account/user_account/operations.yaml`
- canonical：`quwoquan_app/lib/service/user_service/account/user_settings/presentation/settings_page.dart`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 设置审计

- GIVEN 管理身份、Persona 或关系的用户具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“设置审计”对应的公开行为。
- THEN 通过父能力公开契约交付“设置审计”的可观察结果。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`settings-and-device-token`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 设置页账号与隐私配置必须在 owner 登录态下可读写

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：设置页内账号与分身、外观与字号、隐私设置的能力边界清晰，游客态与登录态呈现符合商用品质。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-002"></a>
### OPEN-002 设置审计 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺少能够证明“设置审计”已满足当前规格的真实测试证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。
