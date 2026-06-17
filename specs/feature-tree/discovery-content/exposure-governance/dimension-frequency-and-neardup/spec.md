# L3 Story：dimension-frequency-and-neardup

## 功能说明

在内容硬去重之外，增加作者、标签、话题、内容类型和 near-dup 的维度频控，避免用户连续刷到“不同内容但体验重复”的结果。

## 范围

- 作者、标签、话题、内容类型的窗口频控。
- near-dup 去重：simhash、embedding 或等价签名由后续实现选择。
- 频控优先软降权，必要时硬过滤。
- 频控统计进入曝光健康观测。

## 非目标

- P1 先实现基于 recpolicy 的作者/标签/话题频控与 Jaccard near-dup 软延后；simhash/embedding 签名计算留给后续物化增强。
- 不在 UI 层做本地 near-dup 判断。

## 验收标准

- A1：维度频控阈值来自 recpolicy。
- A2：near-dup 定义有单一真相源，不由 UI 或测试私造签名。
- A3：频控触发率进入 `frequency_cap_filter_rate`，near-dup 进入 `near_dup_filter_rate`。
- A4：频控不能导致空 feed，必须有保底策略。
