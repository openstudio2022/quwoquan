# DEPRECATED - 端侧命令已迁移至根级

自 2026-02-24 起，所有命令统一在仓库根目录 `.cursor/commands/` 下管理。
本目录下的命令不再更新，请使用根级正式命令链路。

## 正式根级命令

- `/explore` → 探索与澄清
- `/prd` → 需求规格基线
- `/design` → 设计基线 + metadata/codegen
- `/dev` → 实施 + `T1~T4` 自验证 + 自动归档
- `/commit` → 读取 `/dev` 自动归档结果后提交
- `/deploy` → integration 验证 + 灰度到 prod
- `/verify` / `/audit` → 复核与审计
- `/try` / `/land` → 原型验证与基线化

## 常见旧命令映射

| 原命令 | 现在使用 |
|-------|---------|
| `/semantic-audit` | `/audit` |
| `/submit-with-audit` | `/commit` |
| `/opsx-explore` | `/explore` |
| `/opsx-verify` | `/verify` |
| `/opsx-bulk-archive` | `/archive`（仅兼容补归档） |

其余记录 `opsx-*` 命令不再作为正式入口，请改按当前标准链路执行。
