# 开发任务：read-write-middleware-chain

- [ ] 设计：ReadInterceptor、WriteInterceptor 接口定义
- [ ] 设计：Chain 组合模式（按顺序执行）
- [ ] 实现：ReadChain 执行器
- [ ] 实现：WriteChain 执行器
- [ ] 实现：链注册与配置（从 EntityRegistry 加载规则）
- [ ] 集成：Repository 层注入读链/写链
- [ ] 测试：链执行顺序单元测试
- [ ] 测试：链失败中断单元测试
- [ ] gate：集成到 make gate
