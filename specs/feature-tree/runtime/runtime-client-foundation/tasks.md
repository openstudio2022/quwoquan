# L2 任务：runtime-client-foundation

## 当前交付任务

由子节点承载，见：
- `app-locale-infrastructure/arb-gen-l10n-string-extraction/tasks.md` ← 当前迭代

## 搁置任务（带规划）

| 任务 | 搁置原因 | 计划重启条件 |
|---|---|---|
| `app-theme-infrastructure` L3 节点建立与交付 | 本迭代优先解决 i18n 基础设施 | i18n 基础设施交付并通过 gate 后，下一迭代启动 |
| 非 widget 上下文 locale 感知（StateNotifier → AppLocalizations） | 需要 locale Provider 传递机制，与状态管理架构有依赖 | `UITextConstants` 在 lib/ui/ 全量替换后，评估是否展开 |

## 未来演进任务

- 英文翻译填充（`app_en.arb` TODO 占位 → 真实翻译）：接入翻译流程后批量填充
- `lib/features/`、`lib/components/` 中硬编码中文字符串迁移：按功能域逐步展开
- `verify_dart_semantic.py` 扩展 CJK 字面量永久卡点：与 lint 脚本同步提交（由 dart-semantic-gate 子节点落地）
