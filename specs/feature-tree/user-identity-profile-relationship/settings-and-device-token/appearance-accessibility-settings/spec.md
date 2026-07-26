# L3 Story：appearance-accessibility-settings — 外观与字号偏好同步设置 (`appearance-accessibility-settings`)

> 所属能力：[`settings-and-device-token`](../spec.md)

> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为管理应用偏好的用户，
我希望读取并修改外观与可访问性设置，让变更在账号设备间按授权同步，
从而以适合自己的主题、字号和交互方式使用应用。

## 2. 范围与非目标

### In Scope

- “appearance-accessibility-settings — 外观与字号偏好同步设置”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 appearance-accessibility-settings — 外观与字号偏好同步设置

- 必须挂在 `settings-and-device-token` 下，以 metadata / API / audit 为真相源，禁止做成仅本地存储能力。

<a id="req-002"></a>
### REQ-002 必须挂在 settings-and-device-token 下，以 metadata / API / audit 为真相源，禁止做成仅本地存储能力

- 必须挂在 `settings-and-device-token` 下，以 metadata / API / audit 为真相源，禁止做成仅本地存储能力。
- 本地缓存仅用于加速与离线恢复，不能成为最终真相源。
- 本 Story 只定义设置值与同步规则，不负责页面视觉运行时实现；必须与 `app-theme-infrastructure` 通过清晰契约对接。
- 发布：统一生效、简单位为主，优先保证正确性与可回滚。
- 灰度：统一生效，简单位为主。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 appearance-accessibility-settings — 外观与字号偏好同步设置

- GIVEN 管理身份、Persona 或关系的用户具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“appearance-accessibility-settings — 外观与字号偏好同步设置”对应的公开行为。
- THEN 必须挂在 `settings-and-device-token` 下，以 metadata / API / audit 为真相源，禁止做成仅本地存储能力。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`settings-and-device-token`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 appearance-accessibility-settings — 外观与字号偏好同步设置 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺少能够证明“appearance-accessibility-settings — 外观与字号偏好同步设置”已满足当前规格的真实测试证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。
