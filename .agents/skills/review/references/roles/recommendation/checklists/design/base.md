# recommendation · design

- [MUST] 曝光、点击、停留、负反馈到策略版本的归因链完整。
  evidence: recommendation-event-contract
- [MUST] 冷启动、漂移、AB 分桶与量化回滚阈值可观测。
  check: 读取目标 DEC/SLI；缺任一场景或阈值不可计算时判失败。
- [MUST NOT] 以 seed/fixture 或并行事件口径验证推荐。
  check: 读取验证数据与事件 owner；命中 fixture/seed/第二事件定义时判失败。
