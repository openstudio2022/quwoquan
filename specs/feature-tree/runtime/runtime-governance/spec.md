# L2 特性：runtime-governance

## 功能说明
- 提供统一服务治理策略引擎：timeout、retry、circuit-breaker、rate-limit、degrade。
- 提供健康检查与优雅停机能力，确保服务生命周期可控。

## 约束
- 治理策略必须由 runtime-config 驱动，禁止硬编码阈值。
- 治理触发与降级行为必须可观测、可审计、可回滚。
- 策略实现需可同时挂载于 HTTP/RPC/Messaging 链路。

## 验收标准
- A1：治理引擎可在多协议链路一致接入。
- A3：策略可配置、可灰度、可回滚。
- A4：策略触发日志指标可检索。
- A8：策略引擎自动化测试完整。
