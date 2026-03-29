# L3 Scenario: search-storage-topology-and-elasticity

## 节点定位

- `L1_capability`: `global-search-experience`
- `L2_feature`: `search-provider-routing-and-storage-topology`
- `L3_scenario`: `search-storage-topology-and-elasticity`

## 背景与动机

统一搜索最终能否扛住增长，取决于云侧搜索读路径是否具备独立扩展能力。本 Scenario 用来冻结读写分离、多读切片和未来统一读库的边界。

## 功能范围

- 冻结业务写模型与搜索读模型分离。
- 冻结多读切片与每切片独立弹性。
- 冻结缓存、限流、熔断与部分降级的基础原则。
- 冻结未来统一高性能搜索读库的替换边界。

## Out of Scope

- 本期立即迁移到统一高性能读库。
- 指定具体厂商或搜索引擎产品。

## 本阶段交付边界

- 阶段二只收口现有 provider 的搜索读路径护栏、metadata 对齐、请求头审计与验证证据。
- 本期可验证的云侧读路径限定为：
  - `content.post`：`GET /v1/content/posts/search`
  - `circle.circle`：`GET /v1/circles/search`
  - `circle.group`：`GET /v1/circles/{circleId}/groups/search`
  - `entity.homepage`：`GET /v1/homepages/search`、`GET /v1/homepages/{homepageId}/shell`、`GET /v1/homepages/{homepageId}/review-summary`、`GET /v1/homepages/{homepageId}/related-groups`
  - `integration.location_poi`：`GET /v1/integration/location/search`、`GET /v1/integration/location/nearby`
- 本期不新增统一 `/v1/search` 云侧聚合服务，也不把扫描业务主集合定义成长期方案。

## 约束

- 搜索读请求不得长期依赖扫描业务主集合。
- 读模型是派生数据，不承担业务主真相源。
- 多读切片按 objectType 或 query class 拆分，支持独立扩缩容。

## 读路径护栏

1. 所有搜索读请求必须走 metadata 定义的只读 API 路径，端侧 Repository 只能通过 codegen path builder 调用。
2. 所有搜索读请求必须注入 `CloudRequestHeaders` 生成的 page / surface / operation header，用于审计、限流与问题定位。
3. `content / circle / homepage / location` 的搜索结果只允许返回搜索视图或 read shell，不允许把写模型 DTO 当作长期搜索读模型契约。
4. 单个 reader slice 故障时允许按 objectType fail-closed，并通过 typed degrade signal 暴露给统一 `SearchRepository` 与 assistant。
5. assistant `search` tool 复用同一组只读 provider，资源边界由 query-first schema、allowlist 与读侧 header 审计共同约束。

## 验收重点

1. 是否明确了读写分离。
2. 是否明确了多读切片和独立弹性。
3. 是否把未来统一读库限制为 read model 替换，而非主存储迁移承诺。
4. 是否为现有 `content / circle / homepage / location` 读路径补齐了 metadata 对齐与 header 审计证据。
