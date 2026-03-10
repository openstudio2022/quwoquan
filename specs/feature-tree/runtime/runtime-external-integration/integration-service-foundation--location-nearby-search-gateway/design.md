# Design: location-nearby-search-gateway

## 设计决策
- 端侧只请求 integration-service，服务内按配置选择百度/阿里。
- nearby/search 统一返回 `LocationPoi`，不暴露供应商差异。
- 错误语义统一映射为 runtime/errors 结构化错误码。

## 错误码与用户文案（contracts/metadata/integration/location/errors.yaml）

| code | 中文 | 英文 |
|------|------|------|
| `INTEGRATION.USER.location_unavailable` | 暂时无法获取当前位置，请稍后重试 | Current location is unavailable, please retry shortly |
| `INTEGRATION.USER.location_permission_required` | 请开启定位权限后重试 | Location permission is required |
| `INTEGRATION.MIDDLEWARE.upstream_timeout` | 位置服务响应超时，请稍后重试 | Location upstream timed out, please retry |
| `INTEGRATION.SYSTEM.internal_error` | 位置服务异常，请稍后重试 | Location service internal error |

端侧创作入口位置选择器按上述 code 映射展示对应文案；另在权限永久拒绝时展示「请在设置中为本应用开启定位权限」+「去设置」（端侧逻辑，非云端返回）。

## Go 侧错误码与 user_message 统一来源（errors.yaml → 生成物可直接使用）

- **规格**：抛出异常时，code 与 user_message 均来自 `errors.yaml`，禁止在 Go 代码中硬编码。
- **生成物**：`codegen_app_metadata` 从 `integration/location/errors.yaml` 生成 `integration-service/internal/generated/errors.go`，包含：
  - 错误哨兵 `Err*`（`errors.New(code)`）
  - `AppErrorFrom*(debugMessage string) *rerrors.AppError`，user_message 取 `user_message.zh`
- **locale**：Go 服务默认使用 `user_message.zh`；端侧展示由 l10n 按 locale 映射。

## 元数据与 codegen 对齐

- `contracts/metadata/integration/location/service.yaml` 定义 `api_routes` 与 `response_list_key`。
- `make codegen-app` 生成 `IntegrationLocationMetadata`（`integration_location_metadata.g.dart`），包含 `nearbyPath`、`searchPath`、`responseItemsKey`。
- **禁止**：业务代码与测试中硬编码 `'nearby'`、`'items'`、`'/v1/integration/location/nearby'` 等，必须引用 `IntegrationLocationMetadata`。

## LocationPoi 端侧 DTO（与 content 域一致）

- `contracts/metadata/integration/location/projections/location_poi.yaml` 定义 `client_projection`，字段与 `fields.yaml` 的 LocationPoi 对齐。
- `make codegen-app` 生成 `LocationPoiDto`（`location_poi_dto.g.dart`），提供 `fromMap` 解析，字段名、别名、类型全部由 projection 定义。
- **禁止**：业务代码中 `map['name']`、`map['latitude']` 等硬编码，必须使用 `LocationPoiDto.fromMap(item)`。
- CreateLocationService 的 `_parseItems` 改为使用 `LocationPoiDto.fromMap`；CreateLocationOption 改为 `CreateLocationOption.from(LocationPoiDto)` 或由 LocationPoiDto 直接替代。
- **校验**：与 content 域一致。顺序：`make verify-metadata` → `make codegen-app` → 业务逻辑 → `make gate`（含 L1a location_poi_dto_contract_test）。

## 适用场景与约束

- 仅提供列表，不涉及地图拖拽选点。
- 搜索请求为高频输入场景，需支持防抖与取消前序请求。
- 端侧仅通过 integration-service 访问位置能力，不直接对接百度/阿里 SDK。

## 未来演进

- 端侧目录规划：新领域页面置于 `lib/ui`，模型与端云交付置于 `lib/cloud` 下由元数据驱动。
