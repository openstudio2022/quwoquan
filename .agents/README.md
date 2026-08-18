# .agents — 跨 harness 共享层

技能的**唯一真相源**。三家 harness（Cursor / Codex / Claude Code）读到的是同一份文件。

## 为什么技能不放 `.cursor/skills/`

放进任一 harness 的专属目录，另外两家就读不到。`.agents/skills/` 是 Codex 的首选路径，
**Cursor 官方文档也把它与 `.cursor/skills/` 并列为项目级技能目录**（不是兼容路径）；
Claude Code 不扫描该目录，用 `.claude/skills` 符号链接接入。

```
.agents/skills/            ← 技能真相源，直接编辑这里
.claude/skills             → 符号链接到 ../.agents/skills（不要改成实体目录）
CLAUDE.md                  → 一行 @AGENTS.md，把根 AGENTS.md 桥接给 Claude Code

.claude/agents/reviewer.md ← 子代理真相源，直接编辑这里
.codex/agents/reviewer.toml → 生成物，勿手改
```

**不要再建 `.cursor/agents/` 符号链接。** `.claude/agents/` 是 Cursor 文档明列的子代理
目录，Cursor 直接读得到；加符号链接既冗余，又依赖「Cursor 是否跟随 symlink」这一未文档化
行为。另注意 `.agents/agents/` **不是**子代理目录——技能认 `.agents/`，子代理不认。

子代理三家格式不可共用：Claude Code 与 Cursor 读 Markdown + YAML frontmatter，
Codex 读 TOML 且必填 `name` / `description` / `developer_instructions`。
所以 Markdown 留一份真相源，TOML 由脚本生成：

```bash
python3 quwoquan_ops/tools/generate_codex_agents.py          # 生成
python3 quwoquan_ops/tools/generate_codex_agents.py --check  # 门禁用，校验是否最新
```

frontmatter 同时写 `tools:`（Claude Code）与 `readonly:`（Cursor）两个键，各家忽略不认识的键；
生成器把 `readonly: true` 映射为 Codex 的 `sandbox_mode = "read-only"`。

## 载体分配原则

**harness 专属目录只放触发加速器与生成产物，绝不放唯一真相源。**

| 载体 | 放什么 | 谁读 |
|---|---|---|
| `AGENTS.md`（根与嵌套） | 分派协议、生命周期契约、全仓红线 | Cursor、Codex；Claude Code 经 `CLAUDE.md` |
| `.agents/skills/*/SKILL.md` | 工作流技能与 review 派发（含角色/checklist/registry） | 三家 |
| `.claude/agents/*.md` | 子代理执行体定义 | Claude Code、Cursor（经符号链接） |
| `.cursor/rules/*.mdc` | 仅指针：「碰到这些文件时读 X」 | 仅 Cursor |
| `.codex/agents/*.toml` | 由脚本生成，勿手改 | 仅 Codex |

## 已知 harness 差异

**嵌套 `AGENTS.md` 在 Claude Code 中不可见。** Cursor 与 Codex 会在处理某目录下文件时
自动应用该路径上更近的 `AGENTS.md`；Claude Code 只读 `CLAUDE.md`，因此仅能通过根
`CLAUDE.md` 的 `@AGENTS.md` 看到根文件。

**曾尝试并已回滚**的方案：在每个第一方目录放 `CLAUDE.md -> AGENTS.md` 符号链接。
回滚原因是 Cursor 同时读 `AGENTS.md` 与 `CLAUDE.md`，同目录下两者内容相同会让最大的
`quwoquan_app/AGENTS.md`（14.8 KB）有被重复计入上下文的风险，代价高于收益；而
Claude Code 是否沿 symlink 发现嵌套 `CLAUDE.md` 官方也未承诺。

因此当前策略是：**真正需要跨三家生效的规则放 `.agents/skills/`**（Claude Code 经
`.claude/skills` 符号链接可读），嵌套 `AGENTS.md` 只承载 Cursor 与 Codex 的分树细则。
若日后实测确认 Cursor 会对同目录 `AGENTS.md` / `CLAUDE.md` 去重，可以重新评估符号链接方案。

**Codex 无法按名字直接 spawn 项目子代理。** 其 `spawn_agent` 只接受 `agent_type`
加 model/prompt 覆盖，没有「用 `.codex/agents/reviewer.toml` 这个定义」的参数。
变通做法是读该 TOML 的 `developer_instructions` 并作为 prompt 覆盖注入通用 worker。
这正是 review 工作流要求**派发 prompt 自包含**的原因——三家里最弱的那一家决定了下限。

## SKILL.md frontmatter 只用 `name` + `description` + `metadata`

开放规范允许 `license` / `compatibility` / `metadata` / `allowed-tools`，Cursor 文档另有
`paths` / `disable-model-invocation`，但**两边的交集实际只有 `name`、`description`、
`metadata`**。当前 11 个工作流技能只写这三个：`metadata.kind: workflow` 标记完整工作流，
`metadata.command` 声明对应的 Cursor 命令——写进任一家的私有字段就会锁死单家。

### description 里的冒号必须加引号

`description: Do a thing: then another` 会让**整份 frontmatter YAML 解析失败**，
技能在 harness 侧静默不可见（既不报错，也不触发）。本仓库统一用 ` - ` 作分隔符规避。

未加引号的冒号会让技能整个消失或描述变空，且 harness 侧不报任何错误。
`make verify-agent-context-budget` 用真正的 YAML 解析器校验这一点——
**手写的按行 `partition(":")` 会把它读成合法值，从而漏报**。

## 结构约束的机器落点

「可复跑」的含义是**每次 `make gate` 都会重跑**，不是一份声称跑过的记录。
凡能机器判定的，都固化在 `quwoquan_ops/gate/verify_agent_context_budget.py`；
凡依赖真实模型行为的（自动 RESOLVE、并发派发、子代理自包含），只能靠实跑取证。

| 约束 | 落点 |
|---|---|
| 顶层只有完整工作流技能、统一八段模板、HANDOFF 声明唯一合法下游 | `check_workflow_skills` |
| 命令薄壳与 `metadata.command` 双向一一映射、无历史叙述 | `check_workflow_skills` |
| 常驻预算（任一目录 AGENTS.md 合并量 < 32 KiB） | `check_agents_budget` |
| 第三方 AGENTS.md 零容忍 | `check_agents_budget` |
| 规则 globs、`gate:` target、脚本与相对链接真实存在 | `check_rule_pointers` / `check_references` |
| checklist 逐条分级、MUST 绑定 gate 或 check | `check_checklist_grading` |
| registry 以工作流名为键：profile/binding/checklist/role 双向可达、与 SKILL「内置评审」一致、无条件 bundle 内 gate 单一归属 | `check_review_registry` |
| 跨文件重复正文（第二真相源） | `check_duplicate_body` |

每条检查在 `quwoquan_ops/tests/local_contract/gate/` 都有能让它变红的负例——
**文档会漂移，门禁不会**。
