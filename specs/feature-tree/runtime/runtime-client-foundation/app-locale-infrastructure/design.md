# L3 设计：app-locale-infrastructure

## 设计动因

见父节点 `runtime-client-foundation/design.md`。本 L3 聚焦 i18n 实现方案选型。

## 方案对比

| 维度 | 方案 A：扩展静态常量 | 方案 B：ARB + flutter gen-l10n（选定） |
|---|---|---|
| locale 切换 | 不支持 | 原生支持 |
| 参数插值 | 手动字符串拼接 | ARB placeholder 类型安全 |
| plural/gender | 不支持 | ICU message format 支持 |
| codegen 保护 | 无 | `DO NOT EDIT` + hash 比对（同服务端） |
| 工具链 | 无依赖 | `flutter gen-l10n`（官方，intl 已依赖） |
| 迁移成本 | 低（只加常量） | 中（需建 ARB + 更新引用）|
| 未来英文支持 | 需大幅重构 | 只需填充 `app_en.arb` |

选定方案 B 的核心理由：项目 `main.dart` 已声明 `en-US` 为 `supportedLocales` 之一，架构意图明确；方案 A 无法演进到多语言，是技术债。

## 目标架构

```
quwoquan_app/
├── l10n.yaml                         ← gen-l10n 配置
└── lib/
    ├── l10n/
    │   ├── app_zh.arb                ← 中文字符串（手写，canonical）
    │   ├── app_en.arb                ← 英文占位（TODO stubs）
    │   ├── l10n.dart                 ← 手写 BuildContext 扩展
    │   ├── app_localizations.dart    ← [DO NOT EDIT] gen-l10n 产物
    │   ├── app_localizations_zh.dart ← [DO NOT EDIT]
    │   └── app_localizations_en.dart ← [DO NOT EDIT]
    └── core/constants/
        ├── ui_text_constants.dart    ← 保留（非 widget 上下文）
        └── app_strings.dart          ← 保留（非 widget 上下文）
```

## 参数化字符串模式

ARB 中处理带插值的字符串：

```json
"allCommentsCount": "全部评论 {count}",
"@allCommentsCount": {
  "placeholders": {
    "count": { "type": "int" }
  }
}
```

Widget 中使用：`context.l10n.allCommentsCount(_commentsCount)`

## 适用场景与约束

- `context.l10n` 只能在 `BuildContext` 可用的场景使用（widget build、showDialog 回调等）
- `UITextConstants` 继续用于无 `BuildContext` 的场景（Provider、Repository 异常信息等）
- 生成的 `app_localizations*.dart` 通过 `DO NOT EDIT` 标注，与服务端 codegen 产物享受同等保护

## 未来演进

- 英文翻译：`app_en.arb` TODO 占位全部填充后，切换 `main.dart` 默认 locale 测试
- `lib/ui/` + `lib/components/` 迁移：按需在各域 tasks.md 中追加任务
- 非 widget 上下文 locale 感知：通过 `LocaleProvider` (Riverpod) 在 StateNotifier 中获取 locale，替换 `UITextConstants` 的剩余用途
