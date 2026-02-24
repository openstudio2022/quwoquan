# 开发任务：runtime-rpc

**实现状态：INTERFACE ONLY** (38 行，仅类型定义)

- [x] 设计：RPCMetadata/UnaryHandler/UnaryInterceptor 类型定义 — `runtime/rpc/rpc.go`
- [x] 实现：ChainUnaryInterceptors 组合辅助函数
- [ ] 实现：gRPC interceptor runtime（L3）
- [ ] 实现：metadata propagation + status mapping（L4）
- [ ] 实现：observability + governance binding（L5）
- [ ] 测试：gRPC interceptor 单元测试
- [ ] gate：集成到 make gate
