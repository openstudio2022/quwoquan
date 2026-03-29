# circle-group-hybrid-fallback-contract 设计方案

## 方案对比

### 方案 A：remote + local 同时查并融合

缺点：

- 排序复杂度高。
- 成本高，且当前需求没有要求混排。

### 方案 B：云优先，失败或 0 结果时回退本地

优点：

- 与当前需求完全一致。
- 复杂度和成本可控。

## 选型决策

**选定方案：方案 B**

## 关键设计决策

- primary = remote
- fallback trigger = error / timeout / circuit open / zero result
- fallback source = local full results
- response signal = `resolvedFrom=local_fallback`

## metadata / codegen 方案

- `_shared/search/search_routing.yaml`
- `social/circle/service.yaml`

## TDD / ATDD 策略

- `T1_schema`：fallback schema
- `T3_cross_service_integration`：remote failure -> local fallback
