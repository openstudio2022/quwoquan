# L2 Business Capability：搜索 Provider 路由与存储拓扑 (`search-provider-routing-and-storage-topology`)

> 所属领域：[`global-search-experience`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

统一搜索 contract、对象 taxonomy、Provider 路由、显式降级、本地搜索生命周期与云侧派生读模型，为全屏搜索和页面内 picker 提供同一查询边界。

## 2. 范围与非目标

### In Scope

- canonical search(request) tool-facing contract。
- 站内业务对象 provider registry 与统一 hit/citation envelope。
- suggest 本地快速检索与 result 云侧最终结果的执行策略边界。
- 搜索核心的 query normalization、相关性排序、敏感 query 阻断、稳定 tie-break 与 rankReasons。
- assistant web_search/search/app_search alias 到 canonical search 的一致性。
- tag/entity/term-heat 信号进入召回、排序、解释、相关搜索词与推荐 Feed 特征。

### Out of Scope

- 业务主存储向 ES/OpenSearch 迁移。
- 向量/语义召回默认开启。
- 未授权私有聊天内容跨用户检索。

## 3. Journey / Scenario 贡献

- [`JNY-005 / SCN-011`](../../spec.md#scn-011)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：统一搜索 contract、对象 taxonomy、Provider 路由、显式降级、本地搜索生命周期与云侧派生读模型结果。
  - 失败时终态：可解释、可恢复且不伪造成功。
- [`JNY-009 / SCN-019`](../../spec.md#scn-019)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：统一搜索 contract、对象 taxonomy、Provider 路由、显式降级、本地搜索生命周期与云侧派生读模型结果。
  - 失败时终态：可解释、可恢复且不伪造成功。

## 4. Story



- [`canonical-search-contract`](./canonical-search-contract/spec.md)：页面与业务层只看到一个 contract，商用字段以 metadata 为唯一真相源。
- [`circle-group-hybrid-fallback-contract`](./circle-group-hybrid-fallback-contract/spec.md)：fallback 必须返回 typed `resolvedFrom=local_fallback`。
- [`local-search-lifecycle-and-account-isolation`](./local-search-lifecycle-and-account-isolation/spec.md)：定义“本地搜索生命周期与账号隔离”的可观察主路径、失败语义及父能力交接。
- [`search-execution-routing-policy`](./search-execution-routing-policy/spec.md)：定义“搜索执行路由策略”的可观察主路径、失败语义及父能力交接。
- [`search-object-taxonomy-and-provider-registry`](./search-object-taxonomy-and-provider-registry/spec.md)：location 成为 canonical search 可召回的一类对象，且 geo 维度机制仅一套。
- [`search-risky-config-gray-release`](./search-risky-config-gray-release/spec.md)：每个发布 revision 必须绑定兼容镜像范围和配置摘要；环境 overlay 不得包含真实 endpoint 密钥、password 或 token。
- [`search-storage-topology-and-elasticity`](./search-storage-topology-and-elasticity/spec.md)：搜索读请求只走 metadata 只读 API + 注入 CloudRequestHeaders 审计；多读切片按 objectType 独立弹性。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 搜索 Provider 路由与存储拓扑能力组合结果

- content.post / entity.homepage / location.place 等云侧 result 对象走 search-service + ES/OpenSearch 派生读库并返回稳定 matchedTerms/evidence/rankReasons/rankPosition。
- suggest 阶段本地对象与 result 阶段云侧对象边界清晰：chat.* 不上云、不进入最终结果页；integration.location_poi 不作为 canonical result 对象。
- web_search / app_search / search 工具不再输出 fake_* provider，而是 canonical_search envelope 或结构化 degrade signal。
- LLM 检索响应含 hits/citations/degradeSignals/provenance，citation 可追溯 objectType/objectId/provider。
- 敏感 query 被阻断，未实现或无权限 provider 不影响其他 provider 结果。
- 搜索词 queryheat/relatedTerms 与 searchTermAffinity 推荐闭环可证明被排序或 Feed scorer 消费。
- canonical search 的 Provider 路由、结果字段与降级信号必须可由同一公开入口重复执行。

<a id="req-002"></a>
### REQ-002 searchable object 的统一命名、字段归属与 provider 注册

- searchable object 的统一命名、字段归属与 provider 注册。
- 云侧搜索读模型、读写分离、多读切片、每切片独立弹性与未来统一读库替换边界。
- **专用 ES/OpenSearch 集群**是统一搜索读库（`quwoquan_objects` 索引）；独立部署的 `search-service` 承载 canonical `search(request)` 云侧入口 `POST /search` 与 `POST /search/feedback`。
- 各域 remote searchable object 改为 indexer 数据源灌入统一索引；第一方 `gateway` workload 的 `/search` 前缀路由指向 `search-service`。
- 所有 searchable object 必须注册到统一 taxonomy，不允许再以产品接口名作为长期真相源。
- 云侧搜索读路径必须与业务写路径分离。
- 多读切片必须支持独立副本数、独立缓存、独立限流与独立弹性。
- 未来统一高性能搜索读库只允许替换 read model，不改变 canonical contract。
- AI 模型生成的条件必须满足 typed schema、allowlist 与资源上限，不能下推为自由表达式执行。
- canonical contract 必须保持 query-first 和扁平条件结构，不引入复杂布尔嵌套 DSL，优先支持 AI 多次主题拆分调用。

## 6. 契约与依赖

- 上游能力：[`global-search-experience`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 canonical search provider routing 三引擎能力 SIT

- GIVEN 执行“canonical search provider routing 三引擎能力”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“canonical search provider routing 三引擎能力”对应动作。
- THEN content.post / entity.homepage / location.place 等云侧 result 对象走 search-service + ES/OpenSearch 派生读库并返回稳定 matchedTerms/evidence/rankReasons/rankPosition。
- THEN suggest 阶段本地对象与 result 阶段云侧对象边界清晰：chat.* 不上云、不进入最终结果页；integration.location_poi 不作为 canonical result 对象。
- THEN web_search / app_search / search 工具不再输出 fake_* provider，而是 canonical_search envelope 或结构化 degrade signal。
- THEN LLM 检索响应含 hits/citations/degradeSignals/provenance，citation 可追溯 objectType/objectId/provider。
- THEN 敏感 query 被阻断，未实现或无权限 provider 不影响其他 provider 结果。
- THEN 搜索词 queryheat/relatedTerms 与 searchTermAffinity 推荐闭环可证明被排序或 Feed scorer 消费。
- THEN 相同输入经同一公开入口重复执行时保持 Provider 路由、结果字段与降级信号一致。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 local-gamma ES 模拟环境性能与真集群差异

- 类型：`risk`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：local-gamma ES 模拟环境性能与真集群差异
- 完成判定：`SIT-001` 的可观察验收在真 ES 集群上通过，local-gamma 与真集群的性能差异不改变该验收结论。

<a id="open-002"></a>
### OPEN-002 搜索索引写时增量与 ES 重启恢复长稳验证

- 类型：`risk`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：搜索索引写时增量与 ES 重启恢复长稳验证
- 完成判定：`SIT-001` 的可观察验收在写时增量与 ES 重启恢复的长稳场景下持续通过。

<a id="open-003"></a>
### OPEN-003 canonical search provider routing 三引擎能力 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：content.post / entity.homepage / location.place 等云侧 result 对象走 search-service + ES/OpenSearch 派生读库并返回稳定 matchedTerms/evidence/rankReasons/rankPosition。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效
