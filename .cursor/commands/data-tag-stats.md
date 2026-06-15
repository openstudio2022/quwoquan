# data-tag-stats

输出标签体系统计报告。

## 执行

```bash
python3 quwoquan_data/scripts/tags/tag_stats.py          # 文本格式
python3 quwoquan_data/scripts/tags/tag_stats.py --json    # JSON 格式
```

## 输出内容

- 各维度标签数量
- 最大树深度
- 叶子/分支节点比例
- 各维度前 10 大子目录及其标签数
- 地理 vs 非地理标签统计

自然语言等价触发：用户直接描述与本命令目标相同的需求时，也按 `/data-tag-stats` 语义执行；执行前仍需按 `docs/agent_context_contract.md` 完成 Spec Entry / Pre-work Reflection，完成后按 Exit Review 收口。

协议补充：执行前按 `docs/agent_context_contract.md` 完成 Spec Entry / Pre-work Reflection；完成后按 Exit Review 输出证据、门禁结果与剩余风险。
