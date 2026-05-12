---
name: /data-normalize-escalate-source
id: data-normalize-escalate-source
category: Workflow
description: 归一化工作流 · 单来源升级取证阶段
---

## 目标

只对少量疑难来源继续深度补证：

- generic 名称证据不足
- 成员关系模糊
- 权威页未命中或互相冲突
- 图片类型 / 水印状态无法确认

## 输入

- `--authority-result`

## 真实实现

```bash
python3 quwoquan_data/tools/cli.py data normalize-build-escalation-input --authority-result "<authority-result.json>"
```

## 结构化检查

```bash
python3 quwoquan_data/tools/cli.py data normalize-validate-output --stage escalate --result "<escalate-result.json>"
```

## 输出

- `runtime/runs/<batch>/normalization/inputs/escalate/<source_ref>.json`
- `runtime/runs/<batch>/normalization/results/escalate/<source_ref>.json`

## 门禁 / 准出

- 必须符合 `evidence_escalation_result.schema.json`
- 必须显式给出新增证据 URL 或“无法补足”的结论

## 失败后动作

- 仍无法确认：保持 `manual_review_required`

## Trace Keys

- `sourceUrl`
- `pageTitle`
- `authorityResultPath`
