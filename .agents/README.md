# .agents 共享真相源

`.agents/skills/*/SKILL.md` 是 Cursor 与 Codex 共用的 Workflow Skill 唯一 authoring source。宿主专属目录只保留发现薄壳或生成 adapter，不拥有功能、流程或 Review 规范正文。

## 载体分工

| 载体 | 唯一职责 |
|---|---|
| 根/子树 `AGENTS.md` | 全局安全与子树每次变更都成立的不变量 |
| `.agents/skills/*/SKILL.md` | 工作流的触发输入、执行、完成证据、失败停止、条件性交接 |
| Feature spec/design/contracts | 功能行为、设计约束、wire 事实与验收 |
| `review/references/registry.yaml` | workflow primary、profile specialist、预算与命名 evidence |
| `review/references/roles/*/ROLE.md` | 角色视角和盲区，不拥有功能事实/命令 |
| `.cursor/commands/*.md` | 一行式 Skill 入口 |
| `.cursor/agents/*.md` / `.codex/agents/*.toml` | 从中性 Reviewer executor 生成的 adapter |

Reviewer executor 中性源为
`.agents/skills/review/references/reviewer-executor.md`。生成和校验：

```bash
python3 quwoquan_ops/tools/generate_agent_adapters.py
python3 quwoquan_ops/tools/generate_agent_adapters.py --check
```

不手改 adapter。本仓只支持 Cursor 和 Codex，不维护第三套 harness 桥接。

## Skill 形状

frontmatter 只使用开放字段；目录名与 `name` 一致，`metadata.kind: workflow`。所有 Workflow Skill 正文均为五段：

1. 触发与输入
2. 执行
3. 完成证据
4. 失败与停止
5. 条件性交接

各 Skill 就地声明完成和失败，不再跳转共享 completion/interaction 文档。持久交接只在跨会话未完成、环境/发布、多人并行、外部阻断或证据复用时生成。

## 机器门禁

`make verify-agent-context-budget` 检查：

- 根加适用子树 `AGENTS.md` 合并不超过 16KiB。
- 默认 feature manifest 不超过 8KiB，单 Reviewer 规则/profile/checklist 上下文不超过 24KiB。
- Workflow Skill 五段、Cursor command 薄壳、frontmatter 与引用有效性。
- 无规范性 Cursor rule、无 role `references/`、无共享 completion/interaction 跳转。
- checklist 的 MUST/MUST NOT 只绑定 `evidence: <id>` 或客观 `check:`，禁止内嵌 `gate:` 命令。
- Review registry v2、中性 executor 与双 adapter 一致，无退役 harness 入口。
