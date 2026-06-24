# L2 特性：runtime-external-integration

## 功能说明
- 建立外部能力集成层（Integration Service）作为统一网关，承载地图等第三方服务接入。
- 对业务域提供稳定契约，屏蔽百度/阿里等供应商差异，避免业务服务直接耦合外部 SDK/API。

## 适用范围与约束
- 适用于跨业务域复用的外部能力（location、sms、ocr 等）。
- 不承载业务聚合逻辑；仅负责外部能力集成、治理、错误标准化与可观测。
- 外部依赖总表见 `docs/external_service_dependency_registry.md`，机读登记真相源见 `docs/external_service_registry.yaml`。
- 所有新增业务 SaaS 依赖默认必须先登记，再通过 `integration-service` 暴露给 App 或业务服务。
- 对象存储 presign、自托管媒体面、离线公开源抓取、客户端平台能力属于豁免项，但仍必须登记并说明理由。

## 验收标准
- A1：新增 integration-service 基础骨架、配置分层与版本化发布配置。
- A2：特性树与云侧文档同步到位，可进入 deliver。
