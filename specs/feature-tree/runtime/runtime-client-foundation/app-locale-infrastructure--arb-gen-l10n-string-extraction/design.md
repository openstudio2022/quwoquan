# L4 设计：arb-gen-l10n-string-extraction

## 设计动因

见父节点 `app-locale-infrastructure/design.md`。本 L4 关注实施细节决策。

## l10n.yaml 配置

```yaml
arb-dir: lib/l10n
template-arb-file: app_zh.arb
output-localization-file: app_localizations.dart
output-class: AppLocalizations
nullable-getter: false
```

`nullable-getter: false` 确保 `AppLocalizations.of(context)` 直接返回非空，配合 `context.l10n` 扩展使用。

## ARB Key 命名规范

从 `UITextConstants` 迁移时的 key 转换规则：

| UITextConstants 常量名 | ARB key（直接用原名）| 说明 |
|---|---|---|
| `loading` | `loading` | 直接对应 |
| `discoveryTabMoment` | `discoveryTabMoment` | camelCase 保持 |
| `allCommentsCount` | `allCommentsCount` | 新增，带 placeholder |

**规则**：ARB key = `UITextConstants` 的 Dart 常量名（camelCase，去掉 `static const String` 声明部分）。这样迁移时 1:1 对应，减少映射混淆。

## context.l10n 扩展（手写，lib/l10n/l10n.dart）

```dart
import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/l10n/app_localizations.dart';

export 'package:quwoquan_app/l10n/app_localizations.dart';

extension AppLocalizationsX on BuildContext {
  AppLocalizations get l10n => AppLocalizations.of(this);
}
```

`export` 行使调用方只需 `import 'package:quwoquan_app/l10n/l10n.dart'` 即可同时获得类型和扩展，无需两个 import。

## 双轨共存策略（非 widget 上下文）

```
Widget.build()         → context.l10n.xxx        （AppLocalizations）
StateNotifier.state    → UITextConstants.xxx      （保留静态常量）
catch (e)              → UITextConstants.xxx      （保留静态常量）
mock data              → 字符串字面量可保留       （非用户可见文本的 i18n）
```

## 参数化 ARB 设计

对于 `'全部评论 $_commentsCount'`，选择 ICU message 而非 `'${count}'` 字符串拼接：

```json
"allCommentsCount": "全部评论 {count}",
"@allCommentsCount": {
  "description": "Comment count display in article detail",
  "placeholders": {
    "count": {
      "type": "int",
      "example": "42"
    }
  }
}
```

对于 `discovery_page.dart` 中的 `'${delta}小时前'`，需要新增 `hoursAgoTemplate`：

```json
"hoursAgoTemplate": "{delta}小时前",
"@hoursAgoTemplate": {
  "placeholders": {
    "delta": { "type": "int" }
  }
}
```

## 适用场景与约束

- `nullable-getter: false` 要求 `MaterialApp` 中必须包含 `AppLocalizations.delegate`，否则运行时抛出；已在 tasks 中确认先完成 main.dart 修改
- mock 数据中的示例文本（如 `'这篇文章写得太好了，非常有启发性！'`）属于测试 fixture，本次不提取到 ARB

## 未来演进

- 暂无（本 L4 为一次性交付任务，不存在演进路径）
- 后续 `lib/ui/` 分域迁移将复用相同 ARB 体系，无需修改基础设施
