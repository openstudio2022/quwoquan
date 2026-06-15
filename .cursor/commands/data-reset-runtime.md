---
name: /data-reset-runtime
id: data-reset-runtime
category: Workflow
description: 应用数据生成工作流 · full runtime reset
---

## 目标

清空当前 `quwoquan_data/runtime/`，恢复 tracked baseline，重建目录布局。

## 真实实现

```bash
bash quwoquan_data/scripts/util/reset_quwoquan_data_runtime_full.sh
```

## 边界

- 该脚本会删除当前 runtime 下的 generated 数据
- baseline 恢复以当前工作树中的 tracked runtime 文件为准

自然语言等价触发：用户直接描述与本命令目标相同的需求时，也按 `/data-reset-runtime` 语义执行；执行前仍需按 `docs/agent_context_contract.md` 完成 Spec Entry / Pre-work Reflection，完成后按 Exit Review 收口。

协议补充：执行前按 `docs/agent_context_contract.md` 完成 Spec Entry / Pre-work Reflection；完成后按 Exit Review 输出证据、门禁结果与剩余风险。
