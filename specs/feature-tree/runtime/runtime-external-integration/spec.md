# L2 特性：runtime-external-integration

## 功能说明
- 建立外部能力集成层（Integration Service）作为统一网关，承载地图等第三方服务接入。
- 对业务域提供稳定契约，屏蔽百度/阿里等供应商差异，避免业务服务直接耦合外部 SDK/API。

## 适用范围与约束
- 适用于跨业务域复用的外部能力（location、sms、ocr 等）。
- 不承载业务聚合逻辑；仅负责外部能力集成、治理、错误标准化与可观测。

## 验收标准
- A1：新增 integration-service 基础骨架、配置分层与版本化发布配置。
- A2：特性树与云侧文档同步到位，可进入 deliver。
