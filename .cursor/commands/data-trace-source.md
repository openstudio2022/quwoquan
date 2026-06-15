---
name: /data-trace-source
id: data-trace-source
category: Workflow
description: 归一化工作流 · 单来源全链路追查
---

## 目标

按来源 URL、页面标题、`source.md` 路径追查它在归一化工作流中的全部文件引用。

## 输入

- `--batch-label`
- `--source-ref` 或 `--source-md` 或 `--source-url`

## 真实实现

```bash
python3 quwoquan_data/scripts/cli.py data trace-source \
  --batch-label "<batch>" \
  --source-md "<source.md>"
```

## 输出

- `runtime/runs/<batch>/normalization/compiled/trace/<source_ref>.json`

## 门禁 / 准出

- 至少能定位 extract / review / authority 三阶段结果路径

## 失败后动作

- 若找不到来源：先检查 `/data-source-fetch` 是否成功落盘

自然语言等价触发：用户说“追查来源”“这条 source 从哪来”“source 证据链断了”时，也按本命令语义执行。

## Trace Keys

- `sourceUrl`
- `pageTitle`
- `sourceMarkdownPath`

协议补充：执行前按 `docs/agent_context_contract.md` 完成 Spec Entry / Pre-work Reflection；完成后按 Exit Review 输出证据、门禁结果与剩余风险。
