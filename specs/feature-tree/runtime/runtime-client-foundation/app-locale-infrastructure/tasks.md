# L3 任务：app-locale-infrastructure

## 当前交付任务

由子节点承载，见：
- `arb-gen-l10n-string-extraction/tasks.md`

## 搁置任务（带规划）

| 任务 | 搁置原因 | 计划重启条件 |
|---|---|---|
| `lib/features/` 硬编码中文迁移 | 范围大，需逐域排期 | i18n 基础设施交付后，按域优先级排期 |
| `lib/components/` 硬编码中文迁移 | 共享组件影响范围广 | 同上，优先级低于 features |
| 英文翻译填充 | 无英文翻译资源 | 接入翻译流程时批量填充 `app_en.arb` |

## 未来演进任务

- CJK 字面量 lint 规则写入 `verify_dart_semantic.py`，形成永久卡点
- 非 widget 上下文 locale 感知（StateNotifier + LocaleProvider）
