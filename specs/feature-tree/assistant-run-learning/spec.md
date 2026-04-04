# L1 规格：助手运行与学习闭环

## 范围
- Run/Stream、策略模板、学习事件上报、反馈注入、画像提案闭环。

## 功能说明
- 提供助手核心运行能力（同步/流式），并保证与端侧协议兼容和可观测。
- 提供学习数据上报与反馈注入能力，形成可持续优化的学习闭环。
- 提供画像提案回流链路，让助手建议能进入用户资料治理流程。

## 约束
- Run 请求与响应契约必须与端侧 personal_assistant 协议兼容。
- 学习事件、评分卡、反馈统计必须进入 metadata 驱动口径。
- 助手策略发布必须支持灰度与回滚。

## 与父/子节点关系

- 父节点：`assistant-run-learning` L1（助手运行与学习闭环能力边界）
- 关键子节点：
  - `learning-event-feedback-injection`（L2）：统一学习事件、反馈聚合、注入链路
  - `run-stream-policy`（L2）：运行与策略模板
  - `profile-proposal-apply-loop`（L2）：画像提案回流
- `learning-event-feedback-injection` 下与当前 baseline 强相关的子节点：
  - `learning-event-ingestion`（L3）：InteractionEvent / Scorecard 上报与统一事件桥接
  - `learning-event-ingestion--interactionevent-scorecard-schema`（L3）：学习事件 schema、字段分级与幂等

## 相关文档

- [`learning-event-feedback-injection/spec.md`](./learning-event-feedback-injection/spec.md)
- [`learning-event-feedback-injection/learning-event-ingestion/spec.md`](./learning-event-feedback-injection/learning-event-ingestion/spec.md)
- [`learning-event-feedback-injection/plan.yaml`](./learning-event-feedback-injection/plan.yaml)

## 验收标准（L1 重点）
- A1：Run/Stream、学习上报、反馈注入可用。
- A2：助手响应时延与成功率达标。
- A5：反馈 -> 评估 -> 策略更新 -> 灰度 -> 回滚闭环成立。
- A8：协议契约与集成测试可复跑。
