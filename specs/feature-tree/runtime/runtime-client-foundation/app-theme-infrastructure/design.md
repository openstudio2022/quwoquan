# L3 设计：app-theme-infrastructure

## 设计动因

见 `app-theme-infrastructure/spec.md`。本 L3 的核心目标不是“再补一套 token”，而是把现有零散的 `AppTheme / AppColors / AppTypography / AppSpacing / SettingsSemanticConstants / 页面手写 isDark 分支` 收敛成真正可运行、可验证、可推广到全量页面的视觉运行时。

## 上游输入评审

### 1. PRD 输入稳定性

- `spec.md` 已冻结：视觉基线为 `Apple HIG / Cupertino-first`
- `acceptance.yaml` 已冻结：覆盖全量页面、全设备矩阵、深浅色、字号、状态栏、门禁与真机验证
- benchmark 已明确：`Instagram + 小红书 + 微信 + 抖音 + Apple HIG`

### 2. 现状代码评审

当前实现已经暴露出三个结构性问题：

1. `quwoquan_app/lib/main.dart`：仍以 `MaterialApp.router` 为主入口，但 `textScaler` 被固定为 `1.0`，系统字体缩放没有真实接通。
2. `quwoquan_app/lib/core/design_system/theme/app_theme.dart`：当前仅是 seed-based `ThemeData`，并未把设计 token 和 Cupertino 子主题系统化映射进去。
3. `quwoquan_app/lib/core/design_system/providers/theme_provider.dart`、`app/providers/accessibility_provider.dart`：主题、字号、无障碍、响应式状态彼此割裂，尚未形成统一的 `appearance runtime`。

### 3. 依赖与约束评审

- 需要与 `page-layout-semantics`、`dart-semantic-gate` 联动，避免 Cupertino-first 规范只停留在文档。
- 不新建业务 metadata；本 Story 只负责客户端视觉运行时。
- 账号级偏好同步不在本 Story 内实现，由兄弟 Story `appearance-accessibility-settings` 提供设置值和同步契约。

### 4. G1 基线

本次 `/design` 已执行并通过：

- `make -C quwoquan_service verify-metadata`
- `make codegen`
- `make codegen-app`

结论：当前 metadata / codegen 基线健康；本 Story 不新增 metadata 文件，只消费后续账号设置 Story 产出的契约。

## 对标输入分析

| 输入 | 吸收点 | 本 Story 处理方式 |
|---|---|---|
| Apple HIG | Grouped list、navigation、sheet、Dynamic Type、Safe Area、触控热区、克制动效 | 作为视觉语法主标准，优先级最高 |
| Instagram | 轻 UI、内容优先、全局 chrome 稳定 | 用于 feed、详情、沉浸式入口的“弱打扰”原则 |
| 小红书 | 图文信息层级、留白、阅读舒适度 | 用于图文页面与评论阅读密度控制 |
| 微信 | 列表、聊天、设置页的一致性和低认知负担 | 用于工具型页面和高频操作流的秩序 |
| 抖音 | 沉浸式媒体页的深色控制与边缘控件布局 | 仅吸收全屏媒体场景，不外溢到常规页面 |

## 方案对比

| 维度 | 方案 A：继续 Material-first，局部补 Cupertino 外观 | 方案 B：统一 token 驱动的双运行时，保留 `MaterialApp.router` 壳但全局 Cupertino-first（选定） | 方案 C：彻底切换到 `CupertinoApp` + 全量组件重写 |
|---|---|---|---|
| 改造成本 | 低 | 中 | 高 |
| 与现有 router / 插件兼容 | 高 | 高 | 中 |
| Apple 风格一致性 | 低 | 高 | 最高 |
| 落地速度 | 快 | 中 | 慢 |
| 对全量页面可控性 | 低 | 高 | 高 |
| 风险 | 继续积累第二套视觉规则 | 需要统一入口和共享组件，但风险可控 | 对现有 Material 依赖和回归面过大 |
| 适配当前阶段 | 不适合 | 最适合 | 过度设计 |

## 选型决策

**选定方案 B**：保留 `MaterialApp.router` 作为宿主壳层，以统一 token 和 `AppearanceSnapshot` 驱动 `ThemeData + CupertinoThemeData + shared component recipes`，实现全局 `Cupertino-first`。

### 选定理由

- 能兼容当前 `go_router`、第三方插件、现有 App 生命周期，而不需要一次性重写为 `CupertinoApp`
- 能在运行时层统一深浅色、字号、系统栏、安全区与组件语法，真正覆盖全量页面
- 允许分批治理共享组件与页面，但视觉真相源始终保持唯一

## 关键设计决策

### KD-1：建立统一的 `AppearanceSnapshot`

引入不可变运行时快照 `AppearanceSnapshot`，统一承载：

- `themeModeSetting`: `system / light / dark`
- `effectiveBrightness`
- `fontSizePreset`
- `effectiveTextScaler`
- `highContrast`
- `boldText`
- `reduceMotion`
- `breakpointClass`: `compact / regular / expanded`
- `safeAreaProfile`

`main.dart` 只消费该快照，不再分别从 `themeProvider`、`accessibilityProvider`、`responsiveProvider` 取碎片状态。

### KD-2：保留 `MaterialApp.router`，但主题生成改为“双运行时”

根入口仍使用 `MaterialApp.router`，但主题生成改为：

```text
AppearanceSnapshot
  -> AppSemanticTokens
    -> ThemeData
    -> CupertinoThemeData
    -> SystemUiOverlayStyle
    -> Shared Component Recipes
```

原因：

- `MaterialApp.router` 对路由、localizations、现有插件生态兼容更稳
- 通过 `CupertinoTheme`、共享组件封装和语义 gate，可以实现视觉上的 Cupertino-first，而无需强制切换宿主壳

### KD-3：token 分三层，而不是继续堆平铺常量

统一为三层：

1. **Foundation tokens**：颜色、字号梯度、字重、圆角、描边、阴影、热区、动效时长
2. **Semantic tokens**：page / section / card / sheet / toolbar / divider / input / emphasis
3. **Component recipes**：nav bar、tab、grouped list、settings row、bottom sheet、dialog、chat input、message bubble

现有 `SettingsSemanticConstants` 等局部语义常量保留，但逐步内聚到 component recipes，不再各页面自立体系。

### KD-4：统一断点和布局语义

统一采用：

- `compact < 360`
- `regular 360-599`
- `expanded >= 600`

并约束：

- 废弃 `ScreenUtil` 作为主适配方案
- 废弃直接 `MediaQuery` 百分比驱动主要布局
- 手机、平板、横屏、分屏、桌面统一通过语义断点 + 最大内容宽度 + 分栏布局规则控制

### KD-5：Material 退到兼容层，Cupertino 成为主语法

共享组件改造优先级：

1. `App Shell / bottom nav / top nav / tab`
2. `sheet / dialog / grouped list / settings row`
3. `button / input / segmented control / picker`
4. `chat input / message bubble / media toolbar`
5. 业务域页面消费上述组件

原则：

- 新写共享组件默认提供 Cupertino-first recipe
- 业务页面不得继续直接混用 `Scaffold + CupertinoButton + Material bottom sheet` 形成第三种风格

### KD-6：系统栏、安全区与沉浸式媒体页统一归口

`status bar / navigation bar / immersive viewer` 的样式不再由页面手写硬编码控制，而统一由 `AppearanceSnapshot + surface role` 派生。

需要解决的现状问题包括：

- 深色沉浸式页面误用亮度
- 页面退出时未正确恢复系统栏
- 刘海/挖孔/平板分屏下 Safe Area 不一致

### KD-7：门禁从“检测硬编码”升级为“检测风格回流”

现有 `verify_dart_semantic` 继续负责硬编码视觉字面量拦截，本 Story 追加的长期目标是：

- 拦截 Android-first 主视觉组件回流
- 拦截新的 `ScreenUtil` 主布局依赖
- 拦截页面级手写深浅色分支替代全局主题

## TDD / ATDD 策略

### ATDD

按 `acceptance.yaml` A1-A8 驱动，优先冻结：

- 主题模式与根入口行为
- 字号与系统栏策略
- 断点与多设备适配
- 全量页面视觉一致性

### TDD

实施顺序坚持 `Red -> Green -> Refactor`：

1. 先写运行时状态与主题快照测试
2. 再写共享组件 widget / golden 测试
3. 再推进页面分域回归
4. 最后接入语义门禁与真机验证

## Task 与测试层映射

| Task | 核心交付 | 对应验收 | 测试层 |
|---|---|---|---|
| T1 | 定义 `AppearanceSnapshot`、token layering、统一断点与 provider 收敛方案 | A1 A4 A5 | T1 |
| T2 | 改造 `main.dart`、`AppTheme`、系统栏策略，接通 `system/light/dark` 与文字缩放 | A2 A3 A5 | T1 T2 T4 |
| T3 | 建立 Cupertino-first 共享组件 recipes：shell/navigation/tab/list/sheet/dialog/button/input | A1 A4 A7 | T1 T2 |
| T4 | 清理 `ScreenUtil`、百分比布局和页面级手写深浅色分支 | A4 A6 | T2 T4 |
| T5 | 分域推进全量页面迁移：discovery/content/chat/user/circle/assistant/settings/welcome/rtc | A4 A6 A7 | T2 T4 |
| T6 | 建立回归与门禁：semantic gate、golden、UI regression、真机矩阵 | A3 A8 | T1 T2 T4 |

## 未来演进

- 设计 token 元数据化：与 `dart-semantic-gate` 的 `design-token-metadata-registry` 演进方向合并
- iPad / desktop 进阶多栏布局：在 `expanded` 断点稳定后引入更细分的 pane 策略
- 无障碍增强：`reduceTransparency`、更完整的 bold/high-contrast 系统联动
- 主题品牌扩展：在不破坏 Apple HIG 基线的前提下支持有限的域级 accent 差异
