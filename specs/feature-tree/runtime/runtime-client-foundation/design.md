# L2 设计：runtime-client-foundation

## 设计动因

项目已存在 `UITextConstants`（520 行）、`AppStrings`（63 行）两个静态常量文件，以及 `AppColors.dark.*`/`AppColors.light.*` 主题 token。这些是**部分解**：它们集中了字符串，但：

1. **i18n**：无 locale 切换能力，无参数插值，无 plural 支持；`main.dart` 已声明 `supportedLocales: [zh-CN, en-US]` 但缺 `AppLocalizations.delegate`
2. **主题**：token 存在但无动态切换机制，所有页面强制取 `AppColors.light.*` 或 `AppColors.dark.*` 中的一套

本 L2 将这两类能力系统化，参照服务端 `runtime-codegen`、`runtime-config` 的建立方式，在客户端建立同等规格的基础设施。

## 架构定位

```
服务端：runtime-config / runtime-codegen / runtime-errors
          ↕ 端云一体，对称设计
客户端：runtime-client-foundation
         ├── app-locale-infrastructure       (对应 runtime-config：配置/文本资源注入)
         ├── app-theme-infrastructure        (对应 runtime-config：主题资源注入)
         ├── error-permission-display-semantics (云端错误与权限类统一展示语义)
         ├── app-remote-config               (App 远程运营配置：运营参数 / feature flag / LKG 快照)
         └── page-layout-semantics (页面布局统一语义：顶部 leading、内容区、底部栏；不含用户/作者/圈子主页)
```

## 关键决策

| 决策点 | 选项 A | 选项 B（选定） | 原因 |
|---|---|---|---|
| 字符串管理方式 | 继续扩展静态常量 | ARB + `flutter gen-l10n` | 官方标准，支持 locale 切换、plural、参数插值；codegen 保护；与服务端 codegen 理念一致 |
| 非 widget 上下文 | 全部迁移 | 双轨共存：`UITextConstants` 保留 | StateNotifier/catch 无 BuildContext，短期保留常量可降低迁移风险；长期通过 locale 感知异常层演进 |
| 主题切换 | 硬编码分支 | Riverpod Provider 驱动 | 与 Repository mock/remote 切换模式对称 |

## 结构化错误的呈现与导航所有权

错误展示与页面导航是两个不同职责：

- `UiErrorSemanticResolver` 负责把 `RuntimeFailure` / `CloudException` 解析为“发生了什么、可以如何恢复”，不决定页面如何退出。
- 栈内页面的退出只由宿主导航栏的返回按钮负责；底部弹层、全屏模态和对话框的退出只由其模态容器的关闭按钮或 barrier 负责。
- `AppPageErrorState` 不再注入 X 、“返回”或 Home fallback；它只展示错误说明与恢复动作。这避免宿主返回、错误 X、错误 CTA 三重退出并存。
- 区块首屏完全失败使用无卡片外框的 `AppSectionErrorState`；局部数据失败且其它内容仍可用时才使用 `AppSectionErrorCard`；已有数据刷新失败使用 `AppTransientErrorNotice`；追加分页失败使用 `AppListAppendErrorFooter`。
- 错误标题可按业务 surface 定制，原因和恢复动作仍必须来自结构化 semantic；禁止把 Remote 失败改写为空数据。

## 适用场景与约束

- **适用**：Flutter App 在 `lib/ui/`、`lib/components/` 中需要展示用户可见文本的所有 widget 上下文（目录规范见 `specs/01_APP_DIRECTORY_STRUCTURE_BY_DOMAIN.md`）
- **不适用**：Go 服务端错误消息（由 `runtime-errors` 负责）；Dart 代码中纯日志/调试字符串
- **约束**：生成文件 `lib/l10n/app_localizations*.dart` 标注 `DO NOT EDIT`，与服务端 codegen 产物同等保护

## 冷启动品牌静态帧

冷启动原生页、Flutter 第一帧、最终全开帧和应用图标共享同一品牌视觉链：

```text
AppColors / AppTypography / AppSpacing
  -> WelcomeAppearance（唯一花瓣 appearance）
  -> WelcomeStaticFrame / WelcomeFlowerMarkPainter
  -> Flutter runtime + golden + native asset generator
  -> Android launch resources + iOS LaunchScreen assets
```

- 图一高保只作为布局、色彩和字形语言的验收参考，禁止把截图或截图文字烘焙为运行时页面。
- 品牌中文字体固定使用仓内 `Noto Sans SC` 可变字体；其 OFL-1.1、上游 commit 和
  SHA-256 由 `assets/fonts/bundled_fonts_manifest.yaml` 审计，不再维护“临时字体待替换”分支。
- 欢迎页、登录页品牌标与应用图标不得使用不同的透明度/渐变 appearance；花瓣路径、颜色、
  花蕊和开放终态只由 `WelcomeFlowerMarkPainter` 解释。
- Android `launch_background.xml` 与启动色资源由原生资产生成器从 Dart 品牌 token 生成；
  iOS 自适应渐变位图与品牌簇也由同一生成器输出，原生资源不是可独立手调的第二真相源。
- 状态栏、Flutter 布局与原生静态资源分别受 contract/golden 约束；任何 token 变更必须同步
  重生成原生资源并通过首帧同构测试。

## 未来演进

- 主题基础设施（`app-theme-infrastructure`）在本 L2 中作为独立 L3 建立，本次仅建节点，下一迭代交付
- 非 widget 上下文的 locale 感知（StateNotifier 通过 Provider 获取 locale）：在 `UITextConstants` 全量替换后作为演进项
- 英文翻译填充：本次 `app_en.arb` 创建 TODO 占位，后续接入翻译流程时填充
