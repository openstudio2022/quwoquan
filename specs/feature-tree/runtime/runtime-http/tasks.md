# 开发任务：runtime-http

**实现状态：90% COMPLETE** (92 行 facade + observability backend)

- [x] 实现：HTTP facade 包（类型重导出 + wrapper 函数）— `runtime/http/http.go`
- [x] 实现：NewHTTPServerMiddleware/NewLoggedRoundTripper/NewObservedHTTPClient wrapper
- [x] 实现：8 个服务客户端工厂 wrapper
- [x] 修复：NewHTTPServerMiddleware wrapper 编译错误（P0-fix-1）
- [ ] 实现：inbound/outbound context propagation（L4）
- [ ] 实现：endpoint normalization + policy hooks（L5）
- [ ] 测试：HTTP pipeline 单元测试
- [ ] gate：集成到 make gate
