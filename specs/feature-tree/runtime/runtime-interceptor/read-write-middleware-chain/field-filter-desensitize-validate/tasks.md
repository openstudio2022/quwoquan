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
