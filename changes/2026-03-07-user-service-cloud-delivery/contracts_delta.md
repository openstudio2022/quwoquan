# Contracts Delta（contracts-first，必须先完成）

## 云侧 contracts（必需）
- [ ] OpenAPI：`quwoquan_service/contracts/openapi/<service>.v1.yaml`
- [ ] 通用 headers/分页/错误：`quwoquan_service/contracts/openapi/common.yaml`
- [ ] endpoint 归因：`quwoquan_service/contracts/endpoint_catalog.md`
- [ ] 错误码：`quwoquan_service/contracts/error_codes.md`
- [ ] 隐私/安全分级：`quwoquan_service/contracts/privacy_and_security.md`

## 端侧契约对齐（必需）
- [ ] RemoteRepository 不允许“猜字段”：对齐 `items/nextCursor` 等统一结构
- [ ] headers 注入：traceId/requestId/pageId/session/device/appVersion（见 `quwoquan_app/lib/cloud/runtime/cloud_request_headers.dart`）

