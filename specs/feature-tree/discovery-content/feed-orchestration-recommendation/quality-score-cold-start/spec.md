# L3 Story：quality-score-cold-start

## 功能说明

内容冷启动不能依赖行为样本。`quality-score-cold-start` 冻结内容质量分和 `recScore` 投影规格，让数据工程内容、UGC 内容和审核后内容在无行为时仍能按质量参与推荐。

## 范围

- 内容质量分来源：数据工程质量门、媒体完整度、正文结构、标签/实体覆盖、审核状态、作者过往质量。
- `recScore` / `qualityScore` 离线投影到推荐读模型。
- importer、BulkImport 和 PostPublished 投影补齐训练 item 特征字段：`qualityScore/recScore/contentVertical/supplySource/semanticMentionCoverage/mediaCompleteness`。
- 质量分缺失率进入 `quality_score_coverage`。

## 非目标

- 不在 feed 读路径同步计算质量分。
- 不引入深度质量模型或同步 `/v1/score` 质量打分。

## 验收标准

- A1：`recScore` 不再允许长期恒 0 作为商用状态。
- A2：质量分只通过离线/异步投影进入读模型，读路径零打分。
- A3：无行为内容按质量分、探索和多样性参与召回排序。
- A4：质量分覆盖率低于目标时阻断商用准出。
- A5：UGC 与数据工程内容使用同一投影公式；缺失质量分时只允许保守默认值。
