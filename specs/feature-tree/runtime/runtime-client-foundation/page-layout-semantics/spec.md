# L3 Story：页面布局语义 (`page-layout-semantics`)

> 所属能力：[`runtime-client-foundation`](../spec.md)

> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为开发、测试或运维角色，
我希望Cupertino 场景不混用 Material 交互组件（Checkbox/SnackBar），选择态统一 iOS 语义，
从而让调用方获得稳定结果，并让维护者能够定位和恢复失败。

## 2. 范围与非目标

### In Scope

- “页面布局语义”的输入、可观察主路径、失败语义以及与父能力的交接。
- Modal/Stack 顶部导航、设置/列表页面壳、贴底 Sheet、单选/多选选择器和响应式几何。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 页面布局语义

- Cupertino 场景不混用 Material 交互组件（Checkbox/SnackBar），选择态统一 iOS 语义。

<a id="req-002"></a>
### REQ-002 设置类页面统一使用 SettingsSemanticConstants 与块结构

- 设置类页面统一使用 SettingsSemanticConstants 与块结构。
- Cupertino 场景不混用 Material 交互组件（Checkbox/SnackBar），选择态统一 iOS 语义。
- 全屏设置/表单使用 `SettingsInsetFormPageScaffold`；贴底选项/说明使用 `AppBottomModalSurface` 与 `ConversationSheet*`。
- 列表页面使用 `AppListPageScaffold`、`AppListSurface`、`AppListRowCard` 及统一空/错/分页载体。

<a id="req-003"></a>
### REQ-003 对齐要求：圈子一级 tab 必须左对齐并与内容区左边缘一致（使用内容区同一水平内边距语义）

- 对齐要求：圈子一级 tab 必须左对齐并与内容区左边缘一致（使用内容区同一水平内边距语义）
- 视觉约束：主操作与强调色使用蓝色主题（`AppColors.primaryColor`），禁止橘色动作色。
- 稳定性约束：一级 tab 在滚动、切换、面板展开/收起过程中不得出现位置跳变。

<a id="req-004"></a>
### REQ-004 响应式断点与页面 surface 分型单轨

- 断点固定为 compact `<360`、regular `360..599`、expanded `>=600`，组件只消费 `AppSpacing.compactBreakpoint`、`expandedBreakpoint` 与 responsive helper。断点只改变密度、导航壳和列数，不改变 IA、终态、触控热区或几何锚点。
- 全局搜索使用全屏 surface；创作、更多、评论和联系人选择使用保留上方上下文的贴底 surface。选项/说明 sheet 复用 `AppBottomModalSurface`、`ConversationSheet*` 或 `showAppActionSheet`，不得裸建第二套 modal popup。
- 设置/表单页复用 Settings inset scaffold，成员选择页复用 member-picker scaffold；新增或移动受控页同步 canonical settings manifest。Modal leading 使用关闭语义，Stack 子页使用返回语义。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 页面布局语义

- GIVEN 开发、测试或运维角色具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“页面布局语义”对应的公开行为。
- THEN Cupertino 场景不混用 Material 交互组件（Checkbox/SnackBar），选择态统一 iOS 语义。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

<a id="gwt-002"></a>
### GWT-002 响应式断点与页面 surface 分型单轨

- GIVEN 用户在 compact、regular 或 expanded 宽度打开搜索、设置或贴底操作面。
- WHEN 页面选择布局断点、导航 leading 与 surface scaffold。
- THEN 页面只消费 canonical token/scaffold/manifest，且宽度变化不复制产品流程、不破坏上下文或返回语义。

## 6. 依赖

- 前置要求：[`runtime-client-foundation`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 页面布局语义 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺少能够证明“页面布局语义”已满足当前规格的真实测试证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-002"></a>
### OPEN-002 响应式断点与 surface 分型尚缺统一合同

- 类型：`capability_gap`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：尚缺同时覆盖 360/600 断点、canonical settings manifest、Modal/Stack leading 与贴底 surface 分型的直接合同；实现扫描不能代替用户可观察布局证据。
- 完成判定：`GWT-002` 对应行为满足且真实测试 `spec_ref` 有效。
