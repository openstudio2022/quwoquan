# recommendation · dev · base

承接原 `/rec-dev` 与 `/rec-audit`，但**已剔除其中与 Mock 隔离冲突的 seed/fixture 要求**
（见 `ROLE.md` 的「重要更正」）。

## PRE 准入

- [MUST] Story spec 的 GWT 已冻结
  check: GWT 未定却已进入实现，判失败
- [MUST] 推荐指标与回滚阈值已量化
  check: 回滚条件是「效果不好就回滚」这类非量化描述，判失败
- [MUST] 归因链设计已明确：曝光、点击、停留、负反馈各自如何关联回
  `feedRequestId` 与策略版本
  check: 缺任一环的关联方式，判失败

## DURING 执行中

- [MUST NOT] 只改算法而不验证端侧曝光、点击、停留、负反馈的归因链
  check: 四类行为中任一类无法关联回 `feedRequestId` 与策略版本，判失败
- [MUST NOT] 用 fixture、数据库 seed 或派生投影预填构造推荐验证数据；
  只能来自 canonical immutable release activation 与领域公开 command/event
  gate: make verify-app-mock-isolation
- [MUST NOT] 让行为上报契约与云侧事件类型定义分叉
  gate: make verify-behavior-event-type-contract

## POST 自检

- [MUST] 行为事件类型契约一致
  gate: make verify-behavior-event-type-contract
- [MUST] Mock 隔离通过
  gate: make verify-app-mock-isolation
- [MUST] 追加式事实命令准入成立
  gate: make verify-append-only-fact-command-admission
- [SHOULD] 冷启动与召回覆盖已评估：新用户、新内容、长尾内容各有明确策略
- [SHOULD] 已检查结果坍缩风险：是否有指标能发现推荐集中到少数内容

## HANDOFF 交接

- 产出：策略改动点、归因链验证结果、AB 分桶与回滚阈值
- 未决项去向：未验证的归因环节转 `OPEN-###`，标注盲区
- 下一步：POST 评审汇总
- 证据链：上述 gate 输出
