# architect · dev · go-service

适用：改动触及 `quwoquan_service/services/**` 的 Go 服务实现或其 contracts。

## DURING 执行中

- [MUST NOT] 客户端 HTTP/WS/DTO JSON 使用 `_id`；只认 canonical `id` / `postId` 等键
  check: 在本次改动的 wire schema、DTO 与 decoder 里搜 `_id`；除 Mongo/bson 持久层外命中即判失败
- [MUST NOT] 引入契约多轨：版本信封、wire 多键双读、dual-read/dual-write、长期 shim、
  compat/warn-only 逃逸，或为错误实现加 fallback
  check: 读 decoder 与 adapter 变更；同一语义存在两个 wire key、或失败路径回落到兼容分支，判失败
- [MUST NOT] 跨对象直连对方 infrastructure 或共享数据库表；只依赖对方
  domain/application port 或领域事件
  gate: make verify-domain-governance

## POST 自检

- [MUST] 服务架构基线通过
  gate: make verify-service-architecture
- [MUST] 错误码声明与发射一致
  gate: make verify-emitted-error-code-declaration
- [MUST] 对象证据闭包成立（对象扩展时）
  gate: make verify-object-evidence-closure
- [SHOULD] 服务 DDD/CQRS 基线通过
  gate: make verify-service-ddd-cqrs-baseline

## HANDOFF 交接

- 产出：服务侧契约 diff 与实现路径
- 未决项去向：边界或语义存疑项转 `OPEN-###`
- 下一步：POST 评审汇总
- 证据链：上述 gate 的实际输出
