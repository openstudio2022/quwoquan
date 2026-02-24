# 开发任务：runtime-query-api-and-hot-reload

- [ ] 设计：EntityRegistry 查询接口（GetEntity/GetFieldPolicy/GetCapabilities/GetStorageBackend/GetCacheTTL/GetTagTaxonomy）
- [ ] 实现：查询 API 实现 + 未注册实体错误处理
- [ ] 实现：并发安全（RWMutex 或 copy-on-write）
- [ ] 实现：Hot-reload 文件变更检测（fsnotify 或轮询）
- [ ] 实现：Hot-reload 重新加载 + 校验 + 原子替换
- [ ] 实现：Hot-reload 配置开关与灰度支持
- [ ] 实现：加载完成日志（entity 总数、字段总数）
- [ ] 实现：Hot-reload 变更摘要日志
- [ ] 测试：Query API 单元测试（全实体覆盖、未注册实体）
- [ ] 测试：Hot-reload 单元测试（更新、回滚、并发）
- [ ] gate：集成到 make verify + make gate
