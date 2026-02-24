# L2 特性：runtime-assistant

## 功能说明
- SuggestedActionsGenerator：根据 PageContext + 内容分析 + 画像，按 8 种页面场景生成差异化建议操作。
- QA Runner：用户自然语言问答 → 三层上下文组装 → Prompt 构建 → LLM 推理 → SSE 流式输出。
- Content Analyzer：多模态内容理解接口（图片/视频/文章/评论），含 Redis 缓存装饰器。
- buildPrompt：三层上下文优先级组装策略（PageContext > Session > Profile > RAG），Token 管控。

## 约束
- SuggestedActions 返回延迟 < 200ms（不含 LLM 推理部分）。
- QA Runner 流式输出，首 token 延迟 < 1s（取决于 LLM 性能）。
- Content Analyzer 结果缓存 24h（评论总结 1h）。

## 验收标准
- A1：内容详情页返回 3~5 个 Suggested Actions（含总结/问询/搜索/规划）。
- A1：聊天页返回对话总结 + 回复建议。
- A1：圈子页返回关联圈子推荐 + 动态总结。
- A1：用户自然语言提问 → 结合 PageContext 准确回答。
- A8：全组件自动化测试。
