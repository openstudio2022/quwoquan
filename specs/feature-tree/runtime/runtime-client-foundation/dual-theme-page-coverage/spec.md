# L3 Story：全页面深浅色模式覆盖 (`dual-theme-page-coverage`)

> 所属能力：[`runtime-client-foundation`](../spec.md)

> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为开发、测试或运维角色，
我希望页面和组件通过语义色与统一 Theme 自动适配深浅模式，不重复传递 `isDark`，
从而让调用方获得稳定结果，并让维护者能够定位和恢复失败。

## 2. 范围与非目标

### In Scope

- “全页面深色 / 浅色模式覆盖（dual-theme-page-coverage）”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 全页面深浅色模式覆盖

- 页面和组件必须优先使用语义色与统一 Theme 自动适配深浅模式，不重复传递 `isDark`。

<a id="req-002"></a>
### REQ-002 语义色、表面层级与高扇出组件优先收敛

- 优先使用语义色和统一 Theme；只有无法由主题推导的局部状态才允许显式双模式分支。
- **半屏 / Sheet** 与全屏页 **同一套表面层级规则**，禁止浅色页 + 深色 sheet 无依据混用。
- **减少散弹式改页面**：**禁止**以「打开几十个 `*_page.dart` 逐行替换 `Color`」为主路径；**整体顺序**见 `design.md` **「减少散弹式修改的整体策略」** —— 先 **设计系统单入口（`AppColorsFunctional` / Theme 扩展）**，再 **高扇出 `components/` 与子模块**，最后才动 **薄页面装配层**。
- 多屏断点/版式与语义 token 由各自 Story 负责；本 Story 只验收深浅色材质、对比度和组件主题消费。
- 页面不允许以长期豁免绕过深浅色验收；无法满足时必须以阻断 OPEN 记录完成判定。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 全页面深浅色模式覆盖

- GIVEN 开发、测试或运维角色具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 用户切换系统主题并进入全屏页或 Sheet。
- THEN 页面与组件通过统一 Theme 使用语义色和一致表面层级，且不重复传递 `isDark`。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`runtime-client-foundation`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 全页面深浅色模式覆盖验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺少覆盖全屏页与 Sheet 的深浅色真实测试证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。
