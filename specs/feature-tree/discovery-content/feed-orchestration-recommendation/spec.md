# L2 特性：feed-orchestration-recommendation

## 功能说明
- 细化 feed-orchestration-recommendation 特性的功能边界与端云协同行为。
- **端侧反馈 + 实时推荐链路**：发现流/详情由端上报行为（曝光、点击、停留、点赞等）→ 云侧 HotPath/FeedbackRecorder 落库 → 下次 GetFeed 时推荐引擎按 session 做实时排序与去重。本节点覆盖「端云行为上报契约 + feed 请求带 session + 发现流曝光/互动上报」的打通与验收。

## 约束
- 契约与字段策略必须与 OpenAPI 与 metadata 保持一致。

## 验收标准
- A1：功能路径可执行且输出稳定。
- A7：契约一致性校验通过。
- A8：对应自动化测试映射完整。
