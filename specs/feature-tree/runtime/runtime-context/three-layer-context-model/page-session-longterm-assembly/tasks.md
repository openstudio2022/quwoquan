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
