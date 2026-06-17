# L3 Story：time-decay-contextual-ranking

## 功能说明

时间维度不只包含内容 freshness，也包括统计量时间衰减、时段上下文、季节性和事件窗口。该 Story 冻结时间加权统计与上下文化排序规格，避免老统计量长期钉死排序。

## 范围

- CTR、完成率、互动率等统计量按时间加权衰减。
- requestHour、weekday、season、eventWindow 等上下文进入排序策略。
- 时间衰减特征新鲜度进入 SLO。
- 与内容生命周期复活共享季节/事件触发器，但不拥有复活状态机。

## 非目标

- 本轮不实现特征作业或 scorer 改动。
- 不把时间上下文硬编码到 UI。

## 验收标准

- A1：统计量时间衰减替代全量均值作为排序输入。
- A2：时段、季节、事件上下文来自 metadata/feature store。
- A3：时间特征新鲜度进入 `time_decay_feature_freshness`。
- A4：时间策略异常时回退 freshness 与规则排序。
