---
name: /data-process-content
id: data-process-content
category: Workflow
description: 应用数据生成工作流 · 图文加工阶段（含编程助手内容生成）
---

> **真相源对齐**：旧入口 `quwoquan_data/tools/cli.py data process-content` 已废弃。统一真相源为 `qwq-data`（=`python3 quwoquan_data/scripts/cli.py <command>`）。本页保留 phase→动词映射，供加工阶段查阅。

## 目标

对已下载来源完成内容加工。旧 `--phase` 概念映射到当前 `qwq-data` 动词：

| 旧 phase | 当前 `qwq-data` 动词 |
|-------|------|
| `all` | `produce review --materialize`（compose 由 Agent 在 CHECKPOINT 创作后 review 一并出门） |
| `review` / `quality-analysis` | `produce review`（三门 + 事实门 + 质量归因，不通过先回退） |
| `compose` / `generate` | CHECKPOINT 处会话 Agent 创作正文（见 `/data-content-compose`）→ `produce review --materialize` |
| `backfill` | `verify`（实体/标签引用一致性）+ `annotate`（人审补全） |

## 工作流位置

`download` → CHECKPOINT(会话 Agent 创作) → `produce review[--materialize]` → `media check-images` → `annotate` → `verify` → `ship`

> fanout 模式下，以上每个动词都是 **per-ref worker 步骤**：worker 经 `qwq-data object-queue lease-next [--ref <ref>]` 租到单 ref，仅加工该 ref，完成 `object-queue complete`；归并用 `qwq-data task rollup --plan <planId>`。

## 常用调用（qwq-data 真相源）

```bash
# 内容润色生成 + 质量门 + 物料化（替代旧 all/compose/generate）
python3 quwoquan_data/scripts/cli.py produce review --task <taskId> --batch <batchId> --materialize

# 仅质量复核（替代旧 review/quality-analysis），可 per-ref
python3 quwoquan_data/scripts/cli.py produce review --task <taskId> --batch <batchId> --refs "<ref1>,<ref2>"

# 图片安全/版式校验
python3 quwoquan_data/scripts/cli.py media check-images --task <taskId> --batch <batchId> --refs "<ref...>"

# 人审与实体/标签补全（替代旧 backfill 人审段），可 per-ref
python3 quwoquan_data/scripts/cli.py annotate --task <taskId> --batch <batchId> --list --refs "<ref...>"
python3 quwoquan_data/scripts/cli.py verify --scope current
```

## 门禁

- review schema 正确
- 图文标题/正文命中实体 `canonicalName` 或 `label_zh`
- 不得引入第二套未回写的展示名

自然语言等价触发：用户直接描述与本命令目标相同的需求时，也按 `/data-process-content` 语义执行；执行前仍需按 `docs/agent_context_contract.md` 完成 Spec Entry / Pre-work Reflection，完成后按 Exit Review 收口。

协议补充：执行前按 `docs/agent_context_contract.md` 完成 Spec Entry / Pre-work Reflection；完成后按 Exit Review 输出证据、门禁结果与剩余风险。
