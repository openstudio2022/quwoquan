# 响应式断点与宽屏表面

## 断点单一来源

断点语义固定 `compact < 360` / `regular 360-599` / `expanded >= 600`。

- [MUST] 只复用 `AppSpacing.compactBreakpoint` / `AppSpacing.expandedBreakpoint` /
  `AppSpacing.responsiveValue()` / `AppTypography.responsive()`。
- [MUST NOT] 在组件内手写第二套 breakpoint map 或 `width > 900` 式私有阈值
  （跨端版式只能用 `AppSpacing` 断点 token + `AppSpacing.responsiveValue`）。
- [MUST] 断点切换只改密度与留白，信息架构与几何锚点保持不变，不出现布局跳变。
- 大屏只允许放大留白、节奏、芯片宽度与内容最大宽度，不允许新造一套视觉语言；
  小屏只允许收紧密度，不允许破坏触控热区与文字可读性。

## 宽屏 / 跨端表面

跨端（鸿蒙 / Web）的能力优先原则与产品体验同源规则归 architect，见
[../../architect/references/capability-portability.md](../../architect/references/capability-portability.md)。
视觉侧要点：

- 平台差异仅允许出现在：布局密度、导航壳形态（底栏 vs 侧栏/Rail）、内容列数、
  悬停/快捷键/右键等宽屏增强。
- IA、文案 key、空态/错误态/权限态跨平台一致；宽屏 `wide` 大断点扩展同样只经
  `AppSpacing` token 声明，不在页面内私造。
