# search-provider-routing-and-storage-topology 设计方案

## 设计动因

该 L2 的目标是让“统一搜索体验”背后也只有一套统一设计主线，而不是页面统一、接口分裂、执行策略散落、存储实现临时化。

## 上游输入评审

| 输入 | 当前结论 |
|---|---|
| `global-search-experience/spec.md` | 已把统一接口、对象执行策略与云侧存储弹性纳入 L1 |
| `cross-domain-search-journey/*` | Journey 已明确只消费 canonical `search(request)` |
| 历史实现现状 | 仍存在分域搜索方法名、对象边界不一致与远端直扫主集合倾向 |

## 方案对比

### 方案 A：只保留 Journey 文档，不单独建治理层

缺点：

- 页面体验和底层架构会继续耦合。
- provider routing、存储拓扑没有独立真相源。

### 方案 B：直接上统一云侧聚合搜索服务

优点：

- 服务端语义集中。

缺点：

- 与“聊天端侧搜索”前提冲突。
- 过早绑定单一服务形态。

### 方案 C：治理型 L2 + canonical contract + provider registry + read-model topology

优点：

- 同时兼容本地搜索、远端搜索与混合 fallback。
- 不把页面、接口与存储实现绑死在一层。
- 最适合 metadata-first 和后续 codegen。

缺点：

- 需要补一层显式治理文档与 registry。

## 选型决策

**选定方案：方案 C**

## 关键设计决策

### KD1：canonical `search(request)` 是页面与业务层唯一入口

- `suggest` 与 `result` 共用一套接口。
- `objectTypes` 用于声明目标对象，不再新增“建议专用接口”。
- 接口保持 web-search-like 的 query-first 形态：首选一个关键词串 `query`，而不是复杂嵌套表达式。

### KD2：searchable object 必须进入统一 taxonomy

- 对象命名示例：
  - `chat.contact`
  - `chat.conversation`
  - `chat.message`
- `web.document`
  - `circle.group`
  - `content.post`
  - `entity.homepage`
  - `integration.location_poi`

### KD3：provider routing 由 execution mode 决定

- `local_only`
- `remote_only`
- `hybrid_remote_fallback_local`

Journey 和页面只消费结果，不关心执行位置。

### KD4：`circle.group` 采用云优先、本地 fallback

- 云侧失败、超时、熔断或 0 结果时触发 fallback。
- fallback 结果必须带 typed `resolvedFrom` 标记。

### KD5：云侧搜索读路径独立于业务写路径

- 业务写模型继续按域写入 Mongo / PostgreSQL。
- 搜索查询走 projection / read model。
- 读模型按 objectType 拆分，并支持多读切片。

### KD6：未来统一高性能读库只替换 read model 实现

- 不改变 canonical contract。
- 不改变 object taxonomy。
- 不改变页面与业务层调用方式。

### KD7：canonical contract 同时作为 AI agent 检索 tool schema

- App、cloud client、AI agent tool 共用同一个 `SearchRequest / SearchResponse` schema。
- AI 模型允许生成 `query`、`objectTypes`、typed filters、sort hints、limit 与 launch context。
- 接口必须支持 AI 以“主题拆分 -> 关键词检索”方式多次调用，同一回答过程可分别召回 `web.document` 与趣我圈内部对象。
- 模型生成条件必须经过 metadata allowlist 校验与资源边界裁剪，不能生成自由执行表达式、复杂脚本排序或深层布尔 DSL。
- tool 调用保持只读、幂等、可审计、可限流，便于高并发 agent 场景复用。

## metadata / codegen 方案

- `_shared/search/search_contract.yaml`
- `_shared/search/search_objects.yaml`
- `_shared/search/search_routing.yaml`
- `_shared/search/search_storage_topology.yaml`
- `_shared/search/search_tool_schema.yaml`（或由 `search_contract.yaml` 直接生成 tool descriptor）

上述 metadata 统一生成：

- canonical contract
- object registry
- execution mode 常量
- storage topology 常量 / 文档基线
- AI agent 可直接消费的 tool schema / descriptor
- query-first 的 keyword search schema，与 `web.document + quwoquan objects` 的统一召回定义

## 字段演进、迁移/回填、必要时双读双写方案

### 字段演进

- 分域产品接口名 -> canonical objectType + execution mode

### 迁移 / 回填

- 页面层逐步下沉到统一 `search(request)`
- remote provider 逐步从“主集合直查”迁到 search read model

### 双读 / 双写

- 业务数据不做额外跨库双写
- 读模型允许异步投影 / 回放重建

## feature flag、观测、SLO 验证与回滚方案

- 不新增用户可见 feature flag
- 观测：
  - `global_search_provider_error_count`
  - `global_search_remote_reader_latency_ms`
  - `global_search_circle_group_local_fallback_count`
  - `global_search_reader_cache_hit_rate`
  - `global_search_agent_tool_call_count`
  - `global_search_agent_tool_reject_count`
- 回滚：
  - 整版回退到旧搜索实现

## TDD / ATDD 策略

- `T1_schema`：contract、taxonomy、routing、topology metadata、tool schema
- `T3_cross_service_integration`：remote provider、fallback、read model 边界
- `T4_release_rehearsal`：高并发与降级 / 回滚演练，含 agent tool 调用限流、审计与多轮 query-first 检索验证

## plan slice 与 T1~T4 证据矩阵映射

| Slice | 目标 | 主要证据 |
|---|---|---|
| `P1` | 冻结 canonical contract | `T1_schema` |
| `P2` | 冻结 object taxonomy 与 provider registry | `T1_schema` |
| `P3` | 冻结 execution policy 与 `circle.group` fallback | `T1_schema`, `T3_cross_service_integration` |
| `P4` | 冻结本地生命周期与账号隔离 | `T2_module_interaction` |
| `P5` | 冻结云侧搜索读模型拓扑、弹性与 AI agent tool 边界 | `T3_cross_service_integration`, `T4_release_rehearsal` |
