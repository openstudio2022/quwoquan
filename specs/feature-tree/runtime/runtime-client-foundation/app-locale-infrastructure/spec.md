# L3 子特性：app-locale-infrastructure

## 功能说明

Flutter App 国际化（i18n）基础设施模块，建立 ARB + `flutter gen-l10n` 代码生成体系，覆盖：

1. 基础设施搭建（`l10n.yaml`、`lib/l10n/`、`pubspec.yaml generate: true`）
2. 字符串常量迁移（`UITextConstants` / `AppStrings` → `app_zh.arb`）
3. `BuildContext` 扩展访问器（`context.l10n`）
4. `lib/ui/` 下现有硬编码中文字符串清除

## 职责边界

- 负责：i18n 基础设施搭建 + `lib/ui/` 范围内硬编码字符串清除
- 不负责：`lib/ui/`、`lib/components/` 的迁移（列为搁置任务）
- 不负责：`UITextConstants` 删除（双轨共存，非 widget 上下文继续使用）
- 不负责：英文翻译内容填充（`app_en.arb` 使用 TODO 占位）

## 适用范围与约束

- **适用**：Flutter `StatefulWidget` / `StatelessWidget` 的 `build()` 方法中的用户可见文本
- **不适用**：`StateNotifier`、`catch` 块、日志字符串（无 `BuildContext`）
- **前置条件**：`intl: ^0.20.2` 已在 `pubspec.yaml`（✓ 已存在）、`flutter_localizations` SDK 已引入（✓ 已存在）

## 与父/子节点关系

- 父节点：`runtime-client-foundation` L2
- 子节点：`arb-gen-l10n-string-extraction` L4（默认叶子，本次交付）

## 验收标准概要

- A1：`flutter gen-l10n` 生成产物可用，`context.l10n` 在 widget 中可访问
- A7：ARB key 集合与两个常量文件 100% 对齐
- A8：`flutter analyze` 零报错 + CJK 字面量检查脚本通过
