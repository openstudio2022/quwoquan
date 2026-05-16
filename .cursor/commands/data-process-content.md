---
name: /data-process-content
id: data-process-content
category: Workflow
description: 应用数据生成工作流 · 图文加工阶段（含编程助手内容生成）
---

## 目标

对已下载来源完成内容加工，支持以下 `--phase` 阶段：

| phase | 说明 |
|-------|------|
| `all`（默认） | review + compose + review-generated 一步完成 |
| `review` | 仅执行 content-review |
| `compose` | 执行 compose-post + review-generated |
| `quality-analysis` | 生成内容质量分析编程助手任务清单 |
| `generate` | 生成润色/创作编程助手任务清单 |
| `backfill` | 生成实体/标签反向补全编程助手任务清单 |

## 工作流位置

`data download` → normalize 阶段 → **data process-content** → `data publish`

## 常用调用

```bash
# 标准全量加工
python3 quwoquan_data/tools/cli.py data process-content \
  --spec "<spec.yaml>" --topics "<topic_ids>" --targets "alpha,gamma"

# 编程助手内容质量分析
python3 quwoquan_data/tools/cli.py data process-content \
  --phase quality-analysis --spec "<spec.yaml>" --topics "<topic_ids>" --batch-label "<batch>"

# 编程助手内容生成
python3 quwoquan_data/tools/cli.py data process-content \
  --phase generate --spec "<spec.yaml>" --topics "<topic_ids>" --batch-label "<batch>"
```

## 编程助手内容加工流程

1. `--phase quality-analysis` 生成质量分析任务清单
2. 编程助手分析内容质量，标记需润色段落
3. `--phase generate` 生成润色/创作任务清单
4. 编程助手执行润色/创作
5. `--phase backfill` 补全实体/标签关联

## 门禁

- review schema 正确
- 图文标题/正文命中实体 `canonicalName` 或 `label_zh`
- 不得引入第二套未回写的展示名
