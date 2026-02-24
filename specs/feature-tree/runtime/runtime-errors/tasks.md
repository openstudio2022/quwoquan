# 开发任务：runtime-errors

**实现状态：COMPLETE** (核心错误处理模型完成，267 行代码，13 个模块已注册)

- [x] 设计：ErrorCode 结构（Module.Kind.Reason）— `runtime/errors/errors.go`
- [x] 实现：AppError + ErrorResponse + NormalizeError
- [x] 实现：HTTPStatusFromError + WriteHTTPError
- [x] 实现：全模块注册（GATEWAY/ORCH/CONTENT/CIRCLE/USER/CHAT/OPS/ASSISTANT/DB/MQ/CACHE/OSS/CDN）
  - 13 个模块的 module-kind-reason 映射已完成
- [ ] 测试：错误码映射 + 响应格式单元测试
- [ ] 实现：user/debug 分离与脱敏（L4/L5）
- [ ] gate：集成到 make gate
