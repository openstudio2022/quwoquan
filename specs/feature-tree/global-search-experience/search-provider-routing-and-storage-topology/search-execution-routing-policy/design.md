# search-execution-routing-policy 设计方案

## 方案对比

### 方案 A：页面根据对象自己决定怎么搜

缺点：

- 页面逻辑会不断膨胀。
- fallback 无法统一观测。

### 方案 B：planner 基于 registry 和 execution mode 决定

优点：

- 页面完全不关心执行位置。
- fallback 和 degrade 可统一埋点。

## 选型决策

**选定方案：方案 B**

## 关键设计决策

- `local_only`：只查本地 provider。
- `remote_only`：只查远端 provider。
- `hybrid_remote_fallback_local`：先查远端，失败或 0 结果再查本地。
- `SearchResponse` 返回 typed `resolvedFrom`、`degradeSignals`。

## metadata / codegen 方案

- `_shared/search/search_routing.yaml`

## TDD / ATDD 策略

- `T1_schema`：execution mode schema
- `T3_cross_service_integration`：fallback and degrade
