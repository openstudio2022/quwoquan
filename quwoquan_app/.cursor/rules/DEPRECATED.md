# DEPRECATED - 端侧规则已迁移至根级

自 2026-02-24 起，端侧不再单独维护 rules 和 commands。
所有开发均为端云一体化，rules 和 commands 统一在仓库根目录 `.cursor/` 下管理。

## 迁移映射

| 原规则（本目录） | 新规则（根目录 `.cursor/rules/`） |
|----------------|-------------------------------|
| `01-core-coding-standards.mdc` | `09-dart-coding-fullstack.mdc` |
| `02-design-system.mdc` | `09-dart-coding-fullstack.mdc` §2 |
| `03-testing-standards.mdc` | `10-testing-fullstack.mdc` |
| `05-state-management.mdc` | `09-dart-coding-fullstack.mdc` §3 |
| `06-semantic-consistency-audit.mdc` | `07-arch-constraints-fullstack.mdc` §2.1 |

## 迁移映射（Commands）

| 原命令（本目录 `commands/`） | 新命令（根目录 `.cursor/commands/`） |
|---------------------------|----------------------------------|
| `/semantic-audit` | `/fullstack-audit` §1 |
| `/submit-with-audit` | `/submit-with-gate` |
| `/opsx-*` | 根目录 `/opsx-*`（已全部迁移） |

## 注意

- 本目录下的 `.mdc` 文件不会删除（避免破坏历史引用），但不再更新
- 新增或修改规则请前往根目录 `.cursor/rules/`
- 看护流水线完整说明见 `specs/fullstack_guardianship_pipeline.md`
