# L2 特性：runtime-context

## 功能说明
- PageContext Manager：端侧上报 → 解析 → Redis 存储（支持 8 种页面场景，含 userActions 数组）。
- Session Context：从 Redis 热路径获取实时兴趣信号。
- Long-term Profile：user_holistic_profile 五维画像（消费全域事件异步构建）。
- ContextAssembler：三层上下文组装 → 提供给 QA Runner / Suggested Actions / Skill。
- Embedding 生成 → 向量存储（定义在 _vectors/user_context_embedding.yaml）。

## 约束
- ContextAssembler 耗时 < 50ms。
- 画像构建异步，不阻塞用户请求。
- 上下文数据按 classification 策略保护。

## 验收标准
- A1：PageContext 上报 + 画像聚合 + 上下文组装端到端可用。
- A3：异步画像构建 + 可配置 TTL。
- A7：消费 events.yaml 事件，向量与 _vectors/*.yaml 一致。
- A8：全路径自动化测试。
