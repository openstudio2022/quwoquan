# L3 Story：iOS 原生页面壳与门禁（ios-native-page-enforcement） (`ios-native-page-enforcement`)

> 所属能力：[`runtime-client-foundation`](../spec.md)

> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为开发、测试或运维角色，
我希望不禁止 `Material(type: transparency)` 作为 **Cupertino 子树** 的防溢出/字体渲染宿主（与现有 `AppScaffold` 模式一致），
从而让调用方获得稳定结果，并让维护者能够定位和恢复失败。

## 2. 范围与非目标

### In Scope

- “iOS 原生页面壳与门禁（ios-native-page-enforcement）”的输入、可观察主路径、失败语义以及与父能力的交接。
- iOS-facing 页面根壳、导航、反馈、加载、选择与浮层语义。
- `AppColors`、`AppSpacing`、`AppTypography` 与语义常量的唯一视觉来源。
- 对 Material 行为底座的透明隔离和只减不增例外治理。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 iOS 原生页面壳与门禁（ios-native-page-enforcement）

- 不禁止 `Material(type: transparency)` 作为 **Cupertino 子树** 的防溢出/字体渲染宿主（与现有 `AppScaffold` 模式一致）。

<a id="req-002"></a>
### REQ-002 不禁止 Material(type: transparency) 作为 Cupertino 子树 的防溢出/字体渲染宿主（与现有 AppScaffold 模式一致）

- 不禁止 `Material(type: transparency)` 作为 **Cupertino 子树** 的防溢出/字体渲染宿主（与现有 `AppScaffold` 模式一致）。
- 所有被扫描页面都必须满足该约束；不存在空 allowlist 或 baseline，新增违规直接阻断。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 iOS 原生页面壳与门禁（ios-native-page-enforcement）

- GIVEN 开发、测试或运维角色具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“iOS 原生页面壳与门禁（ios-native-page-enforcement）”对应的公开行为。
- THEN 不禁止 `Material(type: transparency)` 作为 **Cupertino 子树** 的防溢出/字体渲染宿主（与现有 `AppScaffold` 模式一致）。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`runtime-client-foundation`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 Material 视觉语义泄露收口

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：对象 `presentation` 层（`lib/service/<service>/<context>/<object>/presentation/**`）与横切 `lib/design_system/**`、`lib/runtime/shell/**` 仍有 Material import、Theme/Colors、MaterialPageRoute 和 Material 控件存量，可能引入 Android 视觉语义或第二套 token。
- 完成判定：`GWT-001` 对应行为在全部被扫描页面满足——运行时扫描报告中的违规信号按真实语义清零或由最小平台适配边界解释；iOS surface、semantic token、深浅色和可访问性均有直接测试证据。
- 依赖：`quwoquan_app/scripts/tools/design_system/scan_material_leaks.py`
  动态报告与 iOS native surface gate。
