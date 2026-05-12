---
name: /data-normalize-authority-source
id: data-normalize-authority-source
category: Workflow
description: 归一化工作流 · 单来源反查权威阶段
---

## 目标

基于 review 结果，对主实体候选做权威确认：

- 简体 canonical 是否成立
- 别名是否成立
- 成员关系是否被权威页或主页正文支持

## 输入

- `--review-result`

## 真实实现

```bash
python3 quwoquan_data/tools/cli.py data normalize-build-authority-input --review-result "<review-result.json>"
```

## 结构化检查

```bash
python3 quwoquan_data/tools/cli.py data normalize-validate-output --stage authority --result "<authority-result.json>"
```

## 输出

- `runtime/runs/<batch>/normalization/inputs/authority/<source_ref>.json`
- `runtime/runs/<batch>/normalization/results/authority/<source_ref>.json`

## 门禁 / 准出

- 必须符合 `authority_backcheck_result.schema.json`
- `authorityMatched` 必须明确
- 若仍无法确认，状态转入 `needs_escalation`

## 失败后动作

- 权威不匹配或证据冲突：进入 `/data-normalize-escalate-source`

## Trace Keys

- `sourceUrl`
- `pageTitle`
- `authorityUrl`
