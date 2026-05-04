# L2 特性：runtime-assistant

## 功能说明
- SuggestedActionsGenerator：根据 PageContext + 内容分析 + 画像，按 8 种页面场景生成差异化建议操作。
- QA Runner：用户自然语言问答 → 三层上下文组装 → Prompt 构建 → LLM 推理 → SSE 流式输出。
- 找私助实时检索：天气等时效性问题先按国家级气象服务入口与可解析的省/自治区/直辖市气象局排序；可维护的城市级官方来源只在检索明确命中时补充，Open-Meteo/MET Norway 等结构化天气 API 仅作为实时数值补充。
- Content Analyzer：多模态内容理解接口（图片/视频/文章/评论），含 Redis 缓存装饰器。
- buildPrompt：三层上下文优先级组装策略（PageContext > Session > Profile > RAG），Token 管控。

## 约束
- SuggestedActions 返回延迟 < 200ms（不含 LLM 推理部分）。
- QA Runner 流式输出，首 token 延迟 < 1s（取决于 LLM 性能）。
- QA Runner 过程抽屉必须保留最终答案生成阶段叙事；检索引用列表视觉上只展示编号标题，保留点击跳转能力，不展示裸 URL。
- Content Analyzer 结果缓存 24h（评论总结 1h）。

## 验收标准
- A1：内容详情页返回 3~5 个 Suggested Actions（含总结/问询/搜索/规划）。
- A1：聊天页返回对话总结 + 回复建议。
- A1：圈子页返回关联圈子推荐 + 动态总结。
- A1：用户自然语言提问 → 结合 PageContext 准确回答。
- A1：用户询问任意城市天气 → 检索来源优先包含国家级与区域级气象权威入口；城市级官方来源只在可解析、可维护或检索命中时补充，端侧引用列表只显示可点击标题。
- A8：全组件自动化测试。
