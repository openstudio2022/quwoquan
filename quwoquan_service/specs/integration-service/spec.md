# Integration Service Spec

## 1. Service Overview

`integration-service` 提供统一外部能力接入网关，首批能力为 location（附近列表、关键词搜索）。
服务目标是屏蔽百度/阿里地图供应商差异，向业务域输出统一 DTO 与错误码。

## 2. API

### GET /v1/integration/location/nearby
- Query: `lat`, `lng`, `radiusMeters`, `limit`
- Response: `LocationPoi[]`
- Notes: 全量通过云侧获取，不涉及地图选点。

### GET /v1/integration/location/search
- Query: `q`, `cityCode`, `lat`, `lng`, `limit`
- Response: `LocationPoi[]`
- Notes: 支持端侧实时输入查询，建议客户端做防抖与取消前序请求。

## 2.1 Provider 主备策略

- 位置供应商支持主用 + 备用配置：`primary_provider`、`backup_provider`
- 调用链路策略：主用失败后自动尝试备用一次；两次均失败才返回失败
- 主用成功时不触发备用，避免额外成本

## 3. Error Model

采用 `INTEGRATION.*` 错误码：
- `INTEGRATION.USER.location_unavailable`
- `INTEGRATION.USER.location_permission_required`
- `INTEGRATION.MIDDLEWARE.upstream_timeout`
- `INTEGRATION.SYSTEM.internal_error`

## 4. Config

配置位于：
- `services/integration-service/configs/default|local|integration|prod/config.yaml`
- `releases/config/integration-service/v*.yaml`

关键项：
- `integration.location.provider` (`baidu` / `amap`)
- `integration.location.primary_provider` (`baidu` / `amap`)
- `integration.location.backup_provider` (`baidu` / `amap`)
- `integration.location.timeout_ms`
- `integration.location.nearby_default_radius_meters`
- `integration.location.nearby_default_limit`
- `integration.location.search_default_limit`

## 5. 可观测与排障

- 所有上游地图调用通过 runtime HTTP client middleware 记录 IO/Process/Exception 日志
- 日志包含：供应商调用方向、endpoint、耗时、状态、错误码，便于定位主备服务可用性
