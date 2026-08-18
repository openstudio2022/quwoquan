# 分级语义与输出格式

所有角色 checklist 的每一条都**必须**带一个分级标签。没有标签的条目视为未完成的 checklist，
由 `make verify-agent-context-budget` 阻断。

## 六档

| 标签 | 裁决 | 含义 |
|---|---|---|
| `[MUST]` | `GATE_BLOCK` | 不满足就停，不进入下一段 |
| `[MUST NOT]` | `GATE_BLOCK` | 出现即停 |
| `[SHOULD]` | `PR_WARN` | 报 finding，需显式裁决 |
| `[SHOULD NOT]` | `PR_WARN` | 报 finding，需显式裁决 |
| `[MAY]` | 提示 | 可选增强，不影响准出 |
| `[ADVISORY]` | 提示 | 背景与经验，不产生 finding |

`GATE_BLOCK` / `PR_WARN` 沿用
[capability-portability](roles/architect/references/capability-portability.md)
已有的语义，不新造第二套裁决词。

## 硬规则：MUST 必须可判定

> **标 `[MUST]` / `[MUST NOT]` 的条目必须绑定 `gate:` 或 `check:` 之一。两者都没有的，
> 一律降级为 `[SHOULD]` / `[SHOULD NOT]`。**

理由：指令文件没有强制力。Anthropic 明确说明 `CLAUDE.md` 是作为普通消息投递、不保证严格
遵守；Cursor 与 Codex 同理。凡是真正不能破的约束，最终都得落到 gate 脚本或 hooks，文档只
负责提高遵守率。允许无法判定的条目标 MUST，只会造成 MUST 通胀——而 MUST 一旦通胀，模型就
会开始整体忽略分级，这正是本次重构要消除的失效模式。

两种绑定：

- **`gate:`** — 一条真实可跑的命令，例如 `make verify-app-mock-isolation`。
  最强，退出码即裁决。目标必须真实存在，由治理门禁校验。
- **`check:`** — 一个客观可判定的谓词，供评审 agent 读文件后裁决。
  必须写清**读什么**和**什么情况判失败**，不能是「检查是否合理」这类主观描述。

```markdown
- [MUST] 页面不得以 Map / dynamic 充当业务展示模型
  gate: make verify-app-page-abc-governance
- [MUST] In Scope 与 Out of Scope 已显式写出
  check: 读本次 HANDOFF 的 scope 段；缺任一侧，或只写 In Scope 未写 Out of Scope，判失败
- [SHOULD] 新增依赖已评估 android/ios/ohos/web 四平台可用性
```

`[SHOULD]` 及以下**不要求**绑定，但写了更好。

## 输出格式

角色返回给 board 的每条 finding 固定四行：

```
[GATE_BLOCK] architect/dev#3 — 页面直接依赖聚合 Repository，绕过 typed port
  依据: .agents/skills/review/references/roles/architect/references/production-wiring-and-test-doubles.md
  证据: lib/service/content_service/.../work_browser_entry_page.dart:42
  修复: 改依赖对象级 ContentPostQuery，删除 repository 注入
```

- 第一行：`[裁决] <角色>/<工作流>#<条目序号> — <一句话结论>`
- `依据`：该条目的真相源路径，让主会话能自行复核
- `证据`：`文件:行` 或命令输出片段。**拿不出证据的 finding 不许提交**，这是抑制评审幻觉的
  主要手段
- `修复`：具体动作，不是「建议关注」

## board 汇总

board 按裁决分三档汇总回主会话，**不做二次加工，不吞掉任何 finding**：

```
GATE_BLOCK 2 条 | PR_WARN 3 条 | 提示 1 条
```

- 存在 `GATE_BLOCK` → 整体判定 `GATE_BLOCK`，主会话必须先修复
- 只有 `PR_WARN` → 逐条显式裁决为「修复」「转 OPEN-###」「判 Out of Scope」三者之一，
  不允许静默略过
- 多个角色对同一处给出冲突结论时，board 不自行裁决，原样并列呈报并标注冲突点
