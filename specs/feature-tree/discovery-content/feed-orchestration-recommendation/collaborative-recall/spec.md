# L3 Story：collaborative-recall

## 功能说明

协同召回是未上深度学习阶段提升推荐准确性的关键非深度能力。它基于用户行为共现离线物化 itemCF/swing i2i 和 u2i 召回源，读路径只消费已物化结果，不同步计算共现。

## 范围

- itemCF / swing i2i 召回。
- u2i 用户兴趣近邻召回。
- 多路召回配额融合和 recall_path 标识。
- 离线 replay 评估协同召回增益。

## 非目标

- P1 先实现读取已物化 `i2i/u2i` 的召回源与多路配额融合；离线物化作业和 replay 评估脚本按后续数据工程切片补齐。
- 不引入双塔 ANN 或深度向量召回。

## 验收标准

- A1：协同召回读路径零计算，只读物化表。
- A2：i2i/u2i 候选进入多路召回配额融合，不替代 tag/hot/social 召回。
- A3：召回效果通过 `collaborative_recall_lift` 和 replay 指标评估。
- A4：可通过 `disable_collaborative_recall_sources` 回滚。
