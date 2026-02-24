# L2 特性：runtime-experiments

## 功能说明
- 提供统一实验分桶与灰度策略运行时，支持策略拉取、缓存、审计追踪。
- 为业务服务提供一致的实验命中结果接口，避免各服务重复实现。

## 约束
- 分桶规则必须稳定可复现，且支持版本化。
- 命中结果需可关联 trace/request 与 experiment audit。
- 策略来源统一由 product-ops 管理，runtime-experiments 只做运行时消费。

## 验收标准
- A1：统一分桶 API 可被服务直接集成。
- A3：策略缓存与 fallback 可配置。
- A5：实验命中可用于运营分析。
- A8：分桶与策略拉取自动化测试完整。
