# L5 横切：holistic-profile-and-embedding

## 功能说明
- **AssistantContextProjector**：消费全域事件（PostViewed、MessageSent、CircleJoined、AssistantInteracted 等）→ 构建 user_holistic_profile。
- **五维画像**：内容偏好、社交关系、圈子参与、聊天话题、助手交互。
- **Embedding 生成**：调用 Embedding API，将画像文本转为向量。
- **向量存储**：按 _vectors/user_context_embedding.yaml 定义的结构存储。

## 实现要点
- **Projector**：订阅 events.yaml 定义的事件；按 userId 聚合；写入 user_holistic_profile 集合。
- **五维聚合**：各维度从对应事件聚合；支持增量更新。
- **Embedding**：画像摘要文本 → Embedding API → 向量；存储到向量库。

## 约束
- 画像构建异步，不阻塞主路径。
- 消费事件与 events.yaml 一致。
- 向量结构与 _vectors/*.yaml 一致。

## 验收标准
- A1：五维画像聚合 + Embedding 生成 + 向量存储端到端正确。
- A3：异步构建，不阻塞。
- A7：消费 events.yaml，向量与 _vectors/*.yaml 一致。
- A8：画像聚合契约测试 + Embedding 单元测试。
