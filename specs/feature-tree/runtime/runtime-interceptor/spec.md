# L2 特性：runtime-interceptor

## 功能说明
- 读链：api_exposure 字段过滤 → classification 脱敏（PII mask, SECRET drop）→ log_policy 日志记录。
- 写链：NOT_NULL/类型校验 → 领域事件发布 hook → observe_metric/ops_metric 指标自动产生。
- 集成到 Repository 层，对业务代码透明。

## 约束
- 拦截规则 100% 由 metadata fields.yaml 驱动，禁止硬编码。
- SECRET 字段在任何对外接口中不得泄露。

## 验收标准
- A1：读链正确过滤/脱敏字段，写链正确校验并触发事件 hook。
- A6：SECRET 字段绝对不暴露，PII 字段按策略脱敏。
- A7：规则与 fields.yaml 完全一致。
- A8：读链/写链全路径自动化测试。
