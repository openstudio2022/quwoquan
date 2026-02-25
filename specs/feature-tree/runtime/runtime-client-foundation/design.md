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
         ├── app-locale-infrastructure  (对应 runtime-config：配置/文本资源注入)
         └── app-theme-infrastructure   (对应 runtime-config：主题资源注入)
```

## 关键决策

| 决策点 | 选项 A | 选项 B（选定） | 原因 |
|---|---|---|---|
| 字符串管理方式 | 继续扩展静态常量 | ARB + `flutter gen-l10n` | 官方标准，支持 locale 切换、plural、参数插值；codegen 保护；与服务端 codegen 理念一致 |
| 非 widget 上下文 | 全部迁移 | 双轨共存：`UITextConstants` 保留 | StateNotifier/catch 无 BuildContext，短期保留常量可降低迁移风险；长期通过 locale 感知异常层演进 |
| 主题切换 | 硬编码分支 | Riverpod Provider 驱动 | 与 Repository mock/remote 切换模式对称 |

## 适用场景与约束

- **适用**：Flutter App 在 `lib/ui/`、`lib/features/`、`lib/components/` 中需要展示用户可见文本的所有 widget 上下文
- **不适用**：Go 服务端错误消息（由 `runtime-errors` 负责）；Dart 代码中纯日志/调试字符串
- **约束**：生成文件 `lib/l10n/app_localizations*.dart` 标注 `DO NOT EDIT`，与服务端 codegen 产物同等保护

## 未来演进

- 主题基础设施（`app-theme-infrastructure`）在本 L2 中作为独立 L3 建立，本次仅建节点，下一迭代交付
- 非 widget 上下文的 locale 感知（StateNotifier 通过 Provider 获取 locale）：在 `UITextConstants` 全量替换后作为演进项
- 英文翻译填充：本次 `app_en.arb` 创建 TODO 占位，后续接入翻译流程时填充
