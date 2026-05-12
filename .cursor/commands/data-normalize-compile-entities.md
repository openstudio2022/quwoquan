---
name: /data-normalize-compile-entities
id: data-normalize-compile-entities
category: Workflow
description: 归一化工作流 · 编译主实体/成员/别名
---

## 目标

汇总单来源三阶段结果，生成：

- `entity_resolution.ndjson`
- `image_resolution.ndjson`
- `pending_resolution.ndjson`

## 输入

- `--batch-label`

## 真实实现

```bash
python3 quwoquan_data/tools/cli.py data normalize-compile-entities --batch-label "<batch>"
```

## 结构化检查

```bash
python3 scripts/verify_normalization_outputs.py --batch-label "<batch>"
```

## 输出

- `runtime/runs/<batch>/normalization/compiled/entity_resolution.ndjson`
- `runtime/runs/<batch>/normalization/compiled/image_resolution.ndjson`
- `runtime/runs/<batch>/normalization/compiled/pending_resolution.ndjson`

## 门禁 / 准出

- `main_entity` 必须为简体 canonical
- `members` 必须带 `evidenceRefs`
- `selectedContentAssets` 不能包含水印图或图标图

## 失败后动作

- 若 pending 太多，回到对应单来源阶段继续补证

## Trace Keys

- `batchLabel`
- `catalogTopicIds`
- `sourceRefs`
