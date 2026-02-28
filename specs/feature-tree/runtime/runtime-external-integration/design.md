# Design: runtime-external-integration

## 设计动因
- 位置服务属于公共外部集成能力，不应归属 content/circle 等业务域。
- 通过独立 integration-service，可在不改端侧和业务域契约的情况下切换供应商。

## 关键决策
- 服务命名采用 `integration-service`（非 `location-service`），保留后续多能力扩展空间。
- 路由统一挂载 `/v1/integration/*`，业务服务按契约调用，不感知具体供应商。

## 适用场景与约束
- 适用于“统一外部集成 + 多业务复用 + 可灰度切换供应商”的场景。
- 约束：集成层仅输出标准 DTO，不透出供应商私有字段到端侧 UI。

## 未来演进
- 从 location 能力扩展到 sms/ocr/push/风控等外部能力。
