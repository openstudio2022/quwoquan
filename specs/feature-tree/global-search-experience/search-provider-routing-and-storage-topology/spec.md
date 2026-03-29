# L2 Feature: search-provider-routing-and-storage-topology

## 节点定位

- `L1_capability`: `global-search-experience`
- `L2_feature`: `search-provider-routing-and-storage-topology`

该节点负责冻结统一搜索 contract、对象 taxonomy、provider routing、fallback 规则、本地搜索生命周期与云侧搜索读模型弹性拓扑。它不直接定义用户可见页面，而是为 `cross-domain-search-journey` 与后续页面内搜索 / picker 搜索提供统一真相源。

## 背景与动机

现有全局搜索虽然已经有统一入口和 Journey，但仍缺少一层明确的搜索治理基线：

1. 页面层看到的是统一体验，底层却仍暴露多个分域方法名，长期会回到第二套接口语义。
2. 聊天对象、本地搜索、`circle.group` fallback 与远端对象之间缺少统一执行策略。
3. 云侧搜索如何承接高并发与成本控制没有冻结，容易继续退回“直接扫业务主集合”的临时实现。

## 子场景拆分

本 L2 冻结 6 个 `L3_scenario`：

| L3 | 职责 |
|---|---|
| `canonical-search-contract` | 统一 `search(request)`、`mode=suggest|result`、统一结果 envelope |
| `search-object-taxonomy-and-provider-registry` | searchable object taxonomy 与 provider registry |
| `search-execution-routing-policy` | `local_only / remote_only / hybrid_remote_fallback_local` 执行策略 |
| `circle-group-hybrid-fallback-contract` | `circle.group` 云优先 / 本地 fallback 合约 |
| `local-search-lifecycle-and-account-isolation` | 本地聊天搜索生命周期与子账号隔离 |
| `search-storage-topology-and-elasticity` | 云侧搜索读模型、读写分离、多读切片与弹性 |

## 能力边界

本 L2 负责：

- 页面与业务层唯一 canonical 搜索接口。
- 供页面与 AI agent 共用的 tool-facing canonical 搜索接口。
- 搜索建议与正式结果共用同一接口，仅通过 `mode` 区分。
- 以单一 `query` 为主输入的 web-search-like 检索语义。
- searchable object 的统一命名、字段归属与 provider 注册。
- `local_only / remote_only / hybrid_remote_fallback_local` 的执行规则。
- `circle.group` 的 fallback typed contract。
- 本地聊天搜索生命周期、账号隔离与删除同步规则。
- 云侧搜索读模型、读写分离、多读切片、每切片独立弹性与未来统一读库替换边界。
- AI 模型可生成的条件边界：`objectTypes`、filters、sort hints、limit、launchContext。
- `web.document` 与趣我圈内部对象共用同一检索接口。

本 L2 不负责：

- 具体搜索引擎、向量库或统一高性能读库的本期实施迁移。
- 低存储设备的阈值与自动淘汰策略。
- assistant runtime / skill / prompt 编排逻辑；但 tool-facing search schema 本身在本 L2 范围内。

## 约束

- 产品与页面层只允许调用 canonical `search(request)`。
- AI agent 只能通过与页面同源的 canonical contract 调用检索，不允许维护第二套 agent-only 搜索接口。
- 所有 searchable object 必须注册到统一 taxonomy，不允许再以产品接口名作为长期真相源。
- 聊天对象固定为 `local_only`。
- `circle.group` 固定为 `hybrid_remote_fallback_local`。
- 云侧搜索读路径必须与业务写路径分离。
- 多读切片必须支持独立副本数、独立缓存、独立限流与独立弹性。
- 未来统一高性能搜索读库只允许替换 read model，不改变 canonical contract。
- AI 模型生成的条件必须满足 typed schema、allowlist 与资源上限，不能下推为自由表达式执行。
- canonical contract 必须保持 query-first 和扁平条件结构，不引入复杂布尔嵌套 DSL，优先支持 AI 多次主题拆分调用。

## 角色分工

- `global-search-experience`: 定义统一搜索治理口径。
- `cross-domain-search-journey`: 消费本 L2 提供的 contract 与 execution policy。
- `messages`: 提供本地聊天 snapshot / sync 真相源。
- `content / circle / entity / integration`: 提供 remote searchable object 的域契约。
- `gateway / orchestrator / platform`: 提供云侧读模型、缓存、限流与观测基础设施。

## 数据生命周期合同

- 本地聊天搜索索引登出不清空，但必须账号隔离。
- 本地消息索引删除与撤回必须同步删索引。
- 云端消息 TTL 与端侧长期保留可以不一致。
- 云侧搜索读模型是派生数据，可按重建 / 回放恢复，不承担业务主存储真相源责任。

## 非功能目标

- `suggest` 高 QPS 路径默认 lexical-only。
- 单个 remote provider 故障不阻塞整个搜索页面。
- 云侧搜索流量不得长期依赖扫描主业务集合。
- 读模型可按 objectType 水平扩展，控制成本。
- tool-facing 搜索接口必须保持幂等、只读、可审计与可限流，支持 agent 高并发调用。
- 同一 agent 回答过程可对 `web.document` 与趣我圈对象执行多轮小查询，接口不得因结构过深而显著增加模型拆解成本。

## 迁移、灰度与回滚要求

- 本次 baseline 不要求立刻迁移到统一高性能读库。
- 若新 contract 或 routing 有问题，整版回退到旧搜索实现，而不是重新暴露第二套产品接口。

## 验收重点

1. 页面与业务层是否真正只有一个 canonical 搜索接口。
2. 本地 / 远端 / fallback 执行策略是否有唯一真相源。
3. 云侧搜索拓扑是否明确禁止“扫描业务主集合”成为长期方案。
