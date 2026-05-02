# L4 对象任务：page-session-longterm-assembly

## 功能说明
- **PageContext Manager**：端侧上报接口 + 解析 + Redis 存储；支持 8 种页面场景（content_detail、feed、chat、circle 等）；含 userActions 数组；TTL 自动过期。
- **Session Context**：从 Redis 热路径（推荐服务写入）读取实时兴趣信号。
- **LongTerm Profile Reader**：从向量存储或 MongoDB 读取 user_holistic_profile。
- **ContextAssembler**：按 userId 聚合三层，耗时 < 50ms。

## 实现要点
- **PageContext API**：POST /v1/context/page，body 含 scene_type、snapshot、userActions；Redis key: context:page:{userId}。
- **Session**：Redis key 与推荐热路径约定一致；读取最近 N 条兴趣信号。
- **LongTerm**：从 user_holistic_profile 集合或向量存储读取。
- **Assembler**：并行读取三层，合并后返回。

## 约束
- PageContext TTL 可配置。
- 组装耗时 < 50ms。
- 按 userId 隔离。

## 验收标准
- A1：PageContext 上报 + 过期 + Session + LongTerm 读取 + 组装端到端正确。
- A2：页面切换时旧 PageContext 自动过期。
- A8：PageContext 单元测试 + ContextAssembler 端到端测试。

## Folded current node `holistic-profile-and-embedding`

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
