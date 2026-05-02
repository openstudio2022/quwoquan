# 开发任务：field-filter-desensitize-validate

- [ ] 实现：api_exposure 字段过滤（drop/readonly/readwrite）
- [ ] 实现：classification 脱敏（PII→mask, SECRET→drop, SENSITIVE→mask_partial）
- [ ] 实现：log_policy 日志（allow/mask/drop）
- [ ] 实现：NOT_NULL 必填校验
- [ ] 实现：类型约束校验（string/int/bool/date 等）
- [ ] 实现：范围/pattern 校验（可选）
- [ ] 测试：过滤单元测试（全 api_exposure 组合）
- [ ] 测试：脱敏单元测试（PII/SECRET/SENSITIVE）
- [ ] 测试：校验单元测试（NOT_NULL/类型/范围）
- [ ] 测试：field_security 契约测试
- [ ] gate：集成到 make gate

## Folded current node `event-hook-metric-emit-integration`

# 开发任务：event-hook-metric-emit-integration

- [ ] 实现：写链领域事件发布 hook（按 events.yaml）
- [ ] 实现：EventPublisher 集成（支持 spy 用于测试）
- [ ] 实现：observe_metric 字段变更 OTEL metric 发射
- [ ] 实现：ops_exposure 运营后台字段可见性控制
- [ ] 测试：事件 hook 单元测试（发布/不发布/payload 不含 SECRET）
- [ ] 测试：指标发射单元测试
- [ ] 测试：端到端契约测试（Post 事件 + UserProfile 指标）
- [ ] gate：集成到 make gate

## 当前交付任务
- [ ] Migrated current node: `event-hook-metric-emit-integration` (from `runtime/runtime-interceptor/read-write-middleware-chain/field-filter-desensitize-validate/event-hook-metric-emit-integration`)
