# data-tag-stats

输出标签体系统计报告。

## 执行

```bash
python3 quwoquan_data/scripts/tag_stats.py          # 文本格式
python3 quwoquan_data/scripts/tag_stats.py --json    # JSON 格式
```

## 输出内容

- 各维度标签数量
- 最大树深度
- 叶子/分支节点比例
- 各维度前 10 大子目录及其标签数
- 地理 vs 非地理标签统计
