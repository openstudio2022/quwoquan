# L4 契约/任务：arb-gen-l10n-string-extraction

## 功能说明

本次交付的可落地任务单元，完整建立 ARB + `flutter gen-l10n` i18n 基础设施，并清除 `lib/ui/` 下所有硬编码 CJK 字符串字面量。

## 交付范围

**基础设施（新建）**

| 文件 | 说明 |
|---|---|
| `quwoquan_app/l10n.yaml` | gen-l10n 配置 |
| `quwoquan_app/lib/l10n/app_zh.arb` | 中文字符串（从 UITextConstants + AppStrings 迁移 + 新增） |
| `quwoquan_app/lib/l10n/app_en.arb` | 英文占位（key 同 zh，值为 TODO stub） |
| `quwoquan_app/lib/l10n/l10n.dart` | `BuildContext` 扩展：`context.l10n` |
| `quwoquan_app/lib/l10n/app_localizations*.dart` | [DO NOT EDIT] gen-l10n 产物 |

**修改（现有文件）**

| 文件 | 变更 |
|---|---|
| `pubspec.yaml` | 添加 `generate: true` + `flutter_localizations` SDK dep（已有则确认） |
| `lib/main.dart` | 添加 `AppLocalizations.delegate` 到 `localizationsDelegates` |
| `lib/ui/content/pages/article_detail_page.dart` | 替换 16 处硬编码中文 → `context.l10n.xxx` |
| `lib/ui/user/pages/author_profile_page.dart` | 替换 40+ 处硬编码中文 → `context.l10n.xxx` |
| `lib/ui/discovery/pages/discovery_page.dart` | 替换 1 处 `'刚刚'` → `context.l10n.justNow` |

**不修改（保留）**

- `lib/core/constants/ui_text_constants.dart` — 保留，用于非 widget 上下文
- `lib/core/constants/app_strings.dart` — 保留，同上

## 适用范围与约束

- **适用**：`lib/ui/` 下三个文件中所有用户可见的 CJK 字符串字面量
- **不适用**：mock 数据中的示例文本（如 `'这篇文章写得太好了'`）——mock 文本不需要 i18n，可保留或抽取为特殊 mock key
- **约束**：`app_localizations*.dart` 禁止手改；英文翻译本次为 `TODO: translate` 占位，不阻塞中文功能

## 参数化字符串清单

| 原始硬编码 | ARB key | 类型 |
|---|---|---|
| `'全部评论 $_commentsCount'` | `allCommentsCount` | `int count` |
| `'交集详情（与 ResonanceSpace 一致，待完整迁移）'` | 保留注释，不提取 | — |
| `'${delta}小时前'` | 已有 `hoursAgo`，改为 `hoursAgoTemplate(delta)` | `int delta` |

## 验收标准

- A1：三个 `lib/ui/` 文件编译通过，运行时中文正常显示
- A7：ARB key 覆盖全量 UITextConstants + AppStrings
- A8：`flutter analyze` 零报错，`flutter gen-l10n` 零报错，CJK 字面量脚本在 `lib/ui/` 内零匹配
