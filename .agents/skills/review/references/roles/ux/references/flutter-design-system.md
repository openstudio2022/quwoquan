# Flutter 设计系统与 iOS 原生画质

覆盖 `quwoquan_app/**/*.dart` 的视觉层。iOS 页面壳、双色覆盖与布局语义的完整行为规格分别在
`specs/feature-tree/runtime/runtime-client-foundation/` 的 `ios-native-page-enforcement`、
`dual-theme-page-coverage`、`page-layout-semantics`；实现前先读目标 L3 spec。

浮层分型、资料页语义、沉浸式浏览器等具体 surface 目录见
[ios-surfaces.md](ios-surfaces.md)。

## MUST NOT：视觉字面量

gate: `python3 quwoquan_app/scripts/runtime/observability/verify_dart_semantic.py`

颜色、间距、圆角、blur、alpha、字号、导航高度、sheet 高度一律禁止字面量。
**token 缺失时先补 token，再写 UI**，不允许「先写死后面再抽」。

```dart
// ❌ 禁止
fontSize: 14.sp
EdgeInsets.all(16.w)
BorderRadius.circular(8)
Color(0xFF1877F2)
SizedBox(width: 44, height: 44)
CupertinoListTile(leadingSize: 44)

// ✅ 必须
style: AppTypography.sm
padding: EdgeInsets.all(AppSpacing.md)
borderRadius: BorderRadius.circular(AppSpacing.borderRadius)
color: AppColors.primaryColor
constraints: BoxConstraints(
  minWidth: AppSpacing.buttonHeight,
  minHeight: AppSpacing.buttonHeight,
)
```

## token 索引

| 用途 | API |
|---|---|
| 主色 / 次色 / 强调 | `AppColors.primaryColor`（含 `Hover`/`Active`）/ `secondaryColor` / `accentColor` |
| 功能色 | `AppColors.success` / `warning` / `error` / `info` |
| 主题 | `AppColors.light.*` / `AppColors.dark.*` |
| 特殊 | `AppColors.special.linkColor` / `onlineColor` / `levelNColor` |
| 基础间距 | `AppSpacing.xs/sm/md/lg/xl` |
| 语义间距 | `AppSpacing.semantic[DesignSemanticConstants.container]?[size] ?? AppSpacing.containerMd` |
| 图标尺寸 | `AppSpacing.iconSmall/iconMedium/iconLarge` |
| 固定高度 | `AppSpacing.bottomNavHeight/tabNavigationHeight/buttonHeight` |
| 圆角 | `AppSpacing.smallBorderRadius/borderRadius/largeBorderRadius` |
| 触控热区 | `AppSpacing.minInteractiveSize`、`AppSpacing.iconButtonMinSizeSm` |

语义间距必须用 `?[]` + `??` 兜底，不允许裸下标。

## 响应式

断点与宽屏表面规则见 [responsive-surfaces.md](responsive-surfaces.md)。

## 无障碍

- [MUST] 可交互热区下限 44x44，主操作 48x48。
- [MUST] 正常文字对比度 4.5:1（AA），大号文字 3:1。
- 深色背景上的文本与图标走 `AppColorsFunctional.getColor`。

## 文案与常量（i18n）

gate: `python3 quwoquan_app/scripts/runtime/observability/verify_dart_semantic.py`

- 用户可见**静态文本** → `UITextConstants.*`，禁止硬编码中英文字面量。
- 含参数的**模板文本**（计数、时间）→ `context.l10n.*Template()`，定义在 `lib/l10n/app_*.arb`。
- **相对时间** → `context.l10n.justNow` / `minutesAgoTemplate` / `hoursAgoTemplate` /
  `daysAgoTemplate` / `monthDayTemplate`，禁止自写「刚刚」「分钟前」。
- 内容类型 → `ContentTypeConstants.*`；概念名称 → `AppConceptConstants.*`；
  设计语义 → `DesignSemanticConstants.*`。
- [MUST NOT] 跨域借用文案 key（例如把图片编辑的「完成」用在圈子选择页）。

## 双色与材质

- [MUST] 所有 iOS-facing UI 同时满足浅色与深色，优先 `AppColors` 动态色与语义表面；
  深色模式不得退化为反色或纯黑白替换。
- [MUST] 材质单层单义：同一视觉层只允许一种主表面。正文与标题区禁止重毛玻璃；
  玻璃只用于 toolbar、sheet、轻量页码指示器等浮层 chrome。
- [MUST NOT] Android 视觉泄露到 iOS-facing UI：默认 ripple、FAB、Snackbar、厚阴影、
  下划线 tab indicator、安卓式密集排版与底栏。必须用 Material 组件时只保留能力底座，
  视觉重映射到 iOS token。
- [MUST] 几何稳定：tab、底部导航、吸顶区的选中态只能用颜色/透明度/字号微差表达，
  禁止粗体跳变、位移跳变或重复实例。
- [MUST] post、关注流卡片、圈子封面与图标、媒体缩略图统一 `contentPreviewCornerRadius`；
  只有大容器用 `largeBorderRadius`。

## 冲突处理

功能需求与本文件冲突时，**先改目标 L3 `spec.md` 或父 L2 `design.md`，再改代码**，
不允许在实现里就地破例。
