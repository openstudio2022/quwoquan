# 开发任务：holistic-profile-and-embedding

- [ ] 实现：AssistantContextProjector — 消费全域事件 → 构建 user_holistic_profile
- [ ] 实现：五维画像聚合逻辑（内容偏好/社交关系/圈子参与/聊天话题/助手交互）
- [ ] 实现：user_holistic_profile 存储（MongoDB 或 Redis）
- [ ] 实现：Embedding 生成（调用 Embedding API）
- [ ] 实现：向量存储（_vectors/user_context_embedding.yaml 结构）
- [ ] 测试：画像聚合契约测试（消费 events.yaml 事件）
- [ ] 测试：Embedding 生成单元测试
- [ ] gate：集成到 make gate
