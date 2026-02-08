# OpenSpec 使用说明

本工程已集成 [OpenSpec](https://github.com/Fission-AI/OpenSpec)（Spec-driven development for AI coding assistants），用于在写代码前与 AI 对齐需求与规格。

## 环境要求

- **Node.js 20.19.0 及以上**（OpenSpec 要求）

## 已完成的集成

- 已将 `@fission-ai/openspec` 加入 `package.json` 的 `devDependencies`
- 已执行 `openspec init --tools cursor`，生成：
  - `openspec/specs/`：**主规格**（当前系统行为，与实现对齐的单一事实来源）
  - `openspec/changes/`：待办/进行中的变更（每个变更一个目录）
  - `.cursor/commands/`：斜杠命令（如 `/opsx:new`）
  - `.cursor/skills/`：OpenSpec 相关技能

**使用前请重启 Cursor IDE**，以便斜杠命令生效。

## 主规格与归档

- **主规格目录**：`openspec/specs/` 下按能力分目录（如 `chat/`、`discovery-feed/`、`main-nav/` 等），每个能力有 `spec.md`。含趣聊、发现、圈子、创作、个人/作者/圈子主页、小趣、评论、内容展示、帖子操作、欢迎与鉴权、应用全局等，与 Figma 原型全量迁移后的实现一致。
- **趣聊与设置/选择页**：详细约定见 `openspec/specs/chat/spec.md`（输入栏、聊天信息页、发起群聊与选择成员、设置页与选择页统一语义 token 等）。
- **已归档的 Figma 迁移**：`openspec/changes/archive/2026-02-06-figma-prototype-full-migration/` 保留完整变更（含 `MIGRATION_SCOPE.md`、`tasks.md`、各 delta spec 副本），供查阅迁移范围与历史任务。

## 常用命令

在 Cursor 对话中使用斜杠命令（推荐）：

| 命令 | 说明 |
|------|------|
| `/opsx:new <变更名>` | 新建一个变更（如 `/opsx:new add-dark-mode`） |
| `/opsx:ff` | 快进：一次性生成 proposal、specs、design、tasks |
| `/opsx:continue` | 创建下一个制品（proposal → specs → design → tasks） |
| `/opsx:apply` | 按 tasks.md 实现代码 |
| `/opsx:archive` | 归档当前变更并把 delta 合并进主规格 |

在终端中使用 npm scripts：

```bash
# 列出当前变更
npm run openspec:list

# 打开交互式仪表盘
npm run openspec:view

# 升级 OpenSpec 后刷新 Cursor 指令
npm run openspec:update
```

## 典型工作流

1. **新建变更**：在 Cursor 里输入 `/opsx:new add-xxx`（`add-xxx` 为 kebab-case 变更名）。
2. **写清需求与设计**：用 `/opsx:ff` 一次生成 proposal、specs、design、tasks，或用 `/opsx:continue` 逐步写。
3. **实现**：用 `/opsx:apply` 让 AI 按 `tasks.md` 实现。
4. **归档**：用 `/opsx:archive` 归档变更并更新主规格。

## 参考

- [OpenSpec 官方仓库](https://github.com/Fission-AI/OpenSpec)
- [Getting Started](https://github.com/Fission-AI/OpenSpec/blob/main/docs/getting-started.md)
- [CLI 参考](https://github.com/Fission-AI/OpenSpec/blob/main/docs/cli.md)

## 可选：关闭遥测

```bash
export OPENSPEC_TELEMETRY=0
```

或 `export DO_NOT_TRACK=1`。
