# 开发任务：runtime-assistant

- [x] 设计：SuggestedActionsGenerator 接口与响应结构 → `runtime/assistant/suggested_actions.go`
- [x] 实现：8 种页面场景差异化建议生成（content_detail/chat/circle/search/feed/profile/...）
- [x] 实现：ContentAnalyzer 接口 + CacheableAnalyzer Redis 缓存装饰器
- [x] 实现：QA Runner — 三层上下文组装 → Prompt 构建 → LLM 调用 → SSE 流式输出
- [x] 实现：buildPrompt — 四层优先级（Page > Session > Profile > RAG）+ Token 截断
- [x] 测试：SuggestedActions 场景测试（content_detail 图片/文章、chat、circle）
- [x] 测试：QA Runner Prompt 构建全层测试
- [x] 测试：Stream 输出格式测试
- [x] gate：go test + go vet 全量通过
