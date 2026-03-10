# L4 对象任务：field-filter-desensitize-validate

## 功能说明
- **Field Filter**：根据 api_exposure（drop/readonly/readwrite）过滤返回字段，drop 字段不出现在响应中。
- **Desensitize**：根据 classification（PII/SECRET/SENSITIVE）脱敏，PII→mask（如手机号 ***1234），SECRET→drop，SENSITIVE→mask_partial。
- **Validate**：根据 constraints（NOT_NULL、类型、范围）校验写入数据，失败返回明确错误。

## 实现要点
- **Filter**：遍历实体字段，按 api_exposure 移除或保留。
- **Desensitize**：按 classification 和 log_policy 执行 mask/drop，支持自定义 mask 函数。
- **Validate**：按 constraints 校验，支持 NOT_NULL、类型、min/max、pattern 等。

## 约束
- 规则 100% 由 fields.yaml 驱动。
- SECRET 字段在任何路径下不得泄露。

## 验收标准
- A1：过滤/脱敏/校验正确执行。
- A6：SECRET 不暴露，PII 按策略脱敏。
- A7：规则与 fields.yaml 一致。
- A8：全场景单元测试 + 契约测试。

## Folded legacy node `event-hook-metric-emit-integration`

# L5 横切：event-hook-metric-emit-integration

## 功能说明
- **Event Hook**：实体 Save 成功后，根据 events.yaml 自动发布领域事件（如 PostCreated），集成 EventPublisher。
- **Metric Emit**：observe_metric=true 的字段变更自动产生 OTEL metric，供监控和告警使用。
- **Ops Integration**：ops_exposure 控制运营后台字段可见性，与 product-ops 集成。

## 实现要点
- **Event Hook**：写链在 Save 成功后调用 EventPublisher.Publish，payload 不含 SECRET 字段。
- **Metric Emit**：按 observe_metric 配置，字段变更时调用 OTEL Counter/Histogram。
- **Ops**：运营后台查询时应用 ops_exposure 过滤，与读链类似但策略独立。

## 约束
- 事件 payload 不含 SECRET 字段。
- 指标发射不阻塞主流程，可异步。

## 验收标准
- A1：Post Save 触发 PostCreated 事件；observe_metric 字段产生指标。
- A4：OTEL metric 正确产生。
- A5：ops_exposure 控制运营可见性。
- A8：事件/指标单元测试 + 契约测试。
