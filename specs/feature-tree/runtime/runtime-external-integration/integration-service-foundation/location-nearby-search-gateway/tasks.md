# 开发任务：location-nearby-search-gateway

## 当前交付任务（metadata → codegen → 业务逻辑 → 测试）

- [x] M1. 新增 location nearby/search 路由声明到 metadata。
- [x] M1b. 新增 response_list_key 到 service.yaml，codegen-app 生成 IntegrationLocationMetadata。
- [x] M1c. 新增 `integration/location/projections/location_poi.yaml`，client_projection 与 fields.yaml 的 LocationPoi 对齐（name/latitude/longitude/address/distanceMeters）。
- [x] M1d. 扩展 codegen_app_metadata：处理 integration/location 的 projections，生成 `LocationPoiDto`（无 base_class，复用 renderStandaloneDtoDart）。
- [x] M1e. integration/location errors 的 codegen-app 支持（类比 content/errors.yaml → IntegrationLocationErrorCode、IntegrationLocationErrorMessages）。
- [x] C1. 重构 CreateLocationService：`_parseItems` 使用 `LocationPoiDto.fromMap`；CreateLocationOption 增加 `CreateLocationOption.from(LocationPoiDto)` 工厂。
- [x] T1b. L1a 契约测试：`test/cloud/integration/location/contract/location_poi_dto_contract_test.dart`，覆盖 fromMap 解析、alias、异常边界（与 content post DTO 契约一致）。
- [x] M2. 新增 LocationProvider 枚举与 LocationPoi 字段规范（metadata 已有，handler 响应按 client_projection 不暴露 provider）。
- [x] B1. integration-service 接口骨架（handler + service）落地。
- [x] B2. 云端错误码映射：runtime 新增 ModuleIntegration，generated errors，location_service 映射 timeout/internal/unavailable。
- [x] T1. nearby/search 契约测试：location_handler_test 覆盖 400/500/504 及错误码解析。
- [x] M1f. 扩展 codegen_app_metadata：从 integration/location/errors.yaml 生成 integration-service/internal/generated/errors.go（Err* 哨兵 + AppErrorFrom*，user_message 取 user_message.zh）；替换当前手写 errors.go。

## 搁置任务（带规划）

（无）

## 未来演进任务

- 端侧 `lib/ui/` 与 `lib/cloud/` 目录规划：新领域页面置于 `lib/ui`，模型与端云交付置于 `lib/cloud` 下由元数据驱动。
