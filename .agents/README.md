# .agents 共享真相源

`.agents/skills/*/SKILL.md` 同时是 Cursor 与 Codex 共用的 Workflow Skill 唯一 authoring source 与宿主发现面。宿主直接读取 metadata 选择 Skill，再加载唯一 `SKILL.md` body；不存在宿主专属 Skill stub、中央 resolver、工作流路由 receipt 或第二份流程正文。

## 载体分工

| 载体 | 唯一职责 |
|---|---|
| 根/子树 `AGENTS.md` | 全局安全与子树每次变更都成立的不变量 |
| `.agents/skills/*/SKILL.md` | Workflow Skill metadata 发现面及触发输入、执行、完成证据、失败停止、条件性交接的唯一正文 |
| Feature spec/design/contracts | 功能行为、设计约束、wire 事实与验收 |
| `review/references/registry.yaml` | workflow primary、profile specialist、预算与命名 evidence |
| `review/references/roles/*/ROLE.md` | 角色视角和盲区，不拥有功能事实/命令 |
| `.cursor/commands/*.md` | 指向同一 Skill body 的一行式显式入口 |
| `.cursor/agents/*.md` / `.codex/agents/*.toml` | 仅从中性 Reviewer executor 生成的 Reviewer projection，不承载 Workflow Skill |

Reviewer executor 中性源为
`.agents/skills/review/references/reviewer-executor.md`。生成和校验：

```bash
python3 quwoquan_ops/tools/generate_agent_adapters.py
python3 quwoquan_ops/tools/generate_agent_adapters.py --check
```

不手改 adapter。本仓只支持 Cursor 和 Codex，不维护第三套 harness 桥接。

## Skill-first 动态闭包

上下文只按 `根 AGENTS -> 宿主读取 .agents/skills metadata -> 唯一 Skill body -> Skill PRE 确定 target -> 最近子树 AGENTS + compact manifest exact ref -> exact contexts/tests` 装配。用户已经给出目标路径时，宿主可先读取最近子树 AGENTS 以遵守路径不变量，但子树不参与自然语言工作流选择。

compact manifest 必须是内容寻址、不可变的 exact ref，由 Skill PRE 生成并在 Review 被显式请求或准出派发时原样复用；开发期 POST 默认零 Reviewer。manifest 不携带 profiles。Review profile 只在 POST 根据 `changed_paths + deliverable` 派生。自然语言与显式入口的同轨性由真实宿主加载同一 Skill body 和生命周期证明，不建立中央 resolver、route receipt、tracked workflow registry，也不允许 manifest-before-skill。

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
