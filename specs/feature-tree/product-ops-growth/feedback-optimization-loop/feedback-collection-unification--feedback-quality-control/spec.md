# L3 特性：feedback-quality-control（反馈质量控制 / 去噪）

## 功能说明

在反馈进入大循环前后做质量控制，避免噪声/过期/样本不足信号污染画像与策略评估：

- **时间衰减去噪**：`InterestDecayJob` 对 `rm_recommend_feature.userFeatures` 四维
  affinities 按半衰期衰减，解 `$inc` 单调累积导致的"旧兴趣永不退场"，使画像反映近期偏好。
- **行为-动作一致性**：`verify_behavior_action_consistency.py` 校验端侧上报行为类型与
  云侧消费动作枚举一致，杜绝"端报了云不认 / 字段丢失"的归因断裂噪声。
- **评估侧样本门槛**：`rec_policy_advisor` 对样本量低于护栏 `minSamples` 的 cohort 一律标
  `hold`（信息不足），绝不据噪声样本下 `recommend_review/reject` 结论。
- **人群命中收敛**：`MatchSegments` 用 AND 语义的结构化 predicate，避免宽松 OR 造成人群泛化噪声。

## 约束

- 衰减半衰期、样本门槛等参数均来自 metadata（`segments.yaml` / `policy.yaml`），禁止硬编码。
- 样本不足只能 `hold`，禁止"零样本默认达标"或"零样本默认 reject"。
- 行为枚举一致性校验是 CI 门禁，不一致即 BLOCK。

## 验收标准

- A1：四维 affinities 随时间衰减，旧兴趣权重单调下降（可由衰减单测证明）。
- A3：样本不足 cohort 一律 hold，不产误导性建议。
- A7：行为-动作枚举端云一致（verify_behavior_action_consistency 绿）。
- A8：对应自动化测试映射完整（见 acceptance.tests.recorded）。
