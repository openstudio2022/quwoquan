# search-storage-topology-and-elasticity 设计方案

## 方案对比

### 方案 A：直接查业务主集合 / 主表

优点：

- 前期实现快。

缺点：

- 难以支撑高并发与成本控制。
- 与业务写路径强耦合。

### 方案 B：按域写入业务库，搜索读路径走 projection / read model

优点：

- 与现有多域业务存储兼容。
- 可按 objectType 做独立扩缩容。

缺点：

- 需要额外读模型建设。

### 方案 C：现在就统一迁移到单一高性能搜索库

优点：

- 长期潜力大。

缺点：

- 迁移面过大，不适合本次 baseline。

## 选型决策

**选定方案：方案 B，并保留未来演进到方案 C 的替换边界**

## 关键设计决策

- 业务写模型继续按域写入现有 Mongo / PostgreSQL。
- 搜索读路径统一走 projection / read model。
- 读侧按 objectType 或 query class 拆成多个 reader slice。
- 每个 reader slice 支持独立副本数、独立缓存、独立限流。
- `suggest` 默认 lexical-only，优先热点缓存。
- 未来统一高性能搜索读库只替换 read model 实现。

## 阶段二收口方案

- `content` reader slice：通过 `SearchPosts` 暴露内容搜索视图，继续与发帖写路径分离。
- `circle` reader slice：通过 `SearchCircles` / `SearchCircleGroups` 暴露圈子与群组读路径，不把圈子写接口当搜索入口。
- `entity` reader slice：通过 `SearchHomepages` 与 `HomepageShell/ReviewSummary/RelatedGroups` 暴露主页搜索与阅读壳层。
- `integration` reader slice：通过 `SearchLocations` / `GetNearbyLocations` 暴露位置搜索，保留外部 provider 网关的独立限流边界。
- 端侧 Repository 对上述读路径一律要求：
  - 使用 metadata codegen 生成的 path / operation / page 常量；
  - 使用 `CloudRequestHeaders` 注入 page 或 surface/operation 头；
  - 通过 contract test 校验 query 参数、路径模板与 header 审计字段；
  - 在统一 `SearchRepository` 中以 typed degrade signal 暴露单 slice 故障。

## metadata / codegen 方案

- 本阶段不新增独立 `search_storage_topology` metadata 文件。
- 读路径真相源继续落在各域 `service.yaml`：
  - `content/post/service.yaml`
  - `social/circle/service.yaml`
  - `entity/homepage/service.yaml`
  - `integration/location/service.yaml`
- App 侧通过 codegen 生成的 `*ApiMetadata`、`*RequestPageIds` 与 `AppUiSurfaces` 常量收口 path / operation / page / surface。

## TDD / ATDD 策略

- `T3_cross_service_integration`：reader topology
- `T2_module_interaction`：统一 `SearchRepository` 对 remote slice fail-closed / fallback 的 typed 行为
- 阶段二仅要求现有 provider 的 contract / degrade evidence 闭环；统一高性能读库迁移与大规模容量演练保留到后续阶段
