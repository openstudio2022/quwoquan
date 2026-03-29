## 兼容说明

连续性评估不再作为独立模型轮次执行。

- 普通问答默认只保留两轮模型交互：
  - 第一轮：`planner.global_plan` 同时完成意图识别、历史沿用/重查/放弃判断、检索设计
  - 第二轮：`synthesizer.final_answer` 在拿到检索结果后同时完成“处理问题”与“生成答案”
- 只有 `replan` 场景才允许扩展到更多轮次
- 历史信息的原则已经并入当前轮主提示词与 `<conversation_spine>.historyAssessment`
- bootstrap 只做轻量规则门控，不再调用独立 `planner.continuity_resolution` 模型模板
