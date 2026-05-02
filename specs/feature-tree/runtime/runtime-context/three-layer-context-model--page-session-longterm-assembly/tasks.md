# 开发任务：page-session-longterm-assembly

- [ ] 实现：PageContext Manager — 上报接口 POST /v1/context/page
- [ ] 实现：PageContext 解析 + Redis 存储（8 种场景、userActions）
- [ ] 实现：PageContext TTL 自动过期
- [ ] 实现：Session Context — 从 Redis 热路径读取
- [ ] 实现：LongTerm Profile Reader — 从存储读取 user_holistic_profile
- [ ] 实现：ContextAssembler — 三层并行读取 + 组装（< 50ms）
- [ ] 测试：PageContext 单元测试（上报/过期/并发/userActions）
- [ ] 测试：ContextAssembler 端到端测试
- [ ] gate：集成到 make gate

## Folded current node `holistic-profile-and-embedding`

# 开发任务：holistic-profile-and-embedding

- [ ] 实现：AssistantContextProjector — 消费全域事件 → 构建 user_holistic_profile
- [ ] 实现：五维画像聚合逻辑（内容偏好/社交关系/圈子参与/聊天话题/助手交互）
- [ ] 实现：user_holistic_profile 存储（MongoDB 或 Redis）
- [ ] 实现：Embedding 生成（调用 Embedding API）
- [ ] 实现：向量存储（_vectors/user_context_embedding.yaml 结构）
- [ ] 测试：画像聚合契约测试（消费 events.yaml 事件）
- [ ] 测试：Embedding 生成单元测试
- [ ] gate：集成到 make gate

## 当前交付任务
- [ ] Migrated current node: `holistic-profile-and-embedding` (from `runtime/runtime-context/three-layer-context-model/page-session-longterm-assembly/holistic-profile-and-embedding`)
