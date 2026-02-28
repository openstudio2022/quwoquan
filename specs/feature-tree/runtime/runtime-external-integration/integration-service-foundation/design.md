# Design: integration-service-foundation

## Approach
- 使用新建 `integration-service` 承接外部能力接入。
- 统一输出 `LocationPoi` 标准 DTO，供应商差异在服务内消化。

## Constraints
- 遵循 runtime 统一能力（errors/config/http/observability）。
- 配置通过 `configs/default|local|integration|prod` 分层管理。
