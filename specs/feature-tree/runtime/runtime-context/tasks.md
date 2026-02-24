# 开发任务：runtime-context

- [x] 设计：三层上下文模型接口（PageContext/SessionContext/LongTermProfile） → `runtime/context/types.go`
- [x] 实现：PageContext Manager — 上报接口 + Redis 存储 + 自动过期 + userActions → `runtime/context/page_context.go`
- [x] 实现：Session Context — 从推荐热路径读取实时兴趣信号 → `runtime/context/assembler.go` (Layer 2)
- [x] 实现：AssistantContextProjector — 消费全域事件 → 构建 user_holistic_profile → `runtime/context/assembler.go`
- [x] 实现：五维画像聚合逻辑（内容偏好/社交关系/圈子参与/聊天话题/助手交互） → `AssistantContextProjector.Project()`
- [x] 实现：Embedding 生成（调用 Embedding API）→ 向量存储 → `VectorSearcher` 接口 + RAG 集成
- [x] 实现：ContextAssembler — 三层上下文组装（< 50ms） → `runtime/context/assembler.go`
- [x] 实现：SuggestedActions Generator — 按页面场景生成建议操作 → `runtime/assistant/suggested_actions.go`
- [x] 实现：QA Runner — 用户自然语言问答 + SSE 流式输出 → `runtime/assistant/qa_runner.go`
- [x] 实现：Content Analyzer 接口 + 缓存装饰器 → `runtime/assistant/suggested_actions.go`
- [x] 测试：PageContext 单元测试（上报/过期/并发/userActions） → `runtime/context/context_test.go`
- [x] 测试：ContextAssembler 端到端测试 → `runtime/context/context_test.go`
- [x] 测试：SuggestedActions 场景测试 → `runtime/assistant/assistant_test.go`
- [x] 测试：QA Runner + Prompt 构建测试 → `runtime/assistant/assistant_test.go`
- [x] gate：集成到 make gate → `go test ./runtime/...` 全量通过
