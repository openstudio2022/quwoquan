# DEPRECATED - 端侧规则已迁移至根级

自 2026-02-24 起，端侧不再单独维护 rules 和 commands。
所有开发均为端云一体化，rules 和 commands 统一在仓库根目录 `.cursor/` 下管理。

## 迁移映射

| 原规则（本目录） | 新规则（根目录 `.cursor/rules/`） |
|----------------|-------------------------------|
| `01-core-coding-standards.mdc` | `02-dart-coding.mdc` |
| `02-design-system.mdc` | `02-dart-coding.mdc` |
| `03-testing-standards.mdc` | `03-testing.mdc` |
| `05-state-management.mdc` | `02-dart-coding.mdc` |
| `06-semantic-consistency-audit.mdc` | `02-dart-coding.mdc` + `03-testing.mdc` |

## 迁移映射（Commands）

| 原命令（本目录 `commands/`） | 新命令（根目录 `.cursor/commands/`） |
|---------------------------|----------------------------------|
| `/semantic-audit` | `/audit` |
| `/submit-with-audit` | `/commit` |
| `/opsx-*` | 根目录正式命令链路：`/explore`、`/prd`、`/design`、`/dev`、`/commit`、`/deploy` |

## 注意

- 本目录下的 `.mdc` 文件不会删除（避免破坏记录引用），但不再更新
- 新增或修改规则请前往根目录 `.cursor/rules/`
- 主线看护与阶段说明见 `specs/00_MASTER_DEVELOPMENT_FLOW.md`
