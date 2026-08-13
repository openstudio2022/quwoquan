# L1 Design：全局搜索体验 (`global-search-experience`)

> 对应规格：[L1 spec](./spec.md)

## 1. 背景与设计目标

- 设计目标：统一搜索覆盖联系人、会话、内容、圈子、主页、地点和网络结果，在本地联想与云侧最终结果之间保持清晰合同，并将反馈归因到搜索和推荐。

## 2. 领域模型与所有权

- authoritative ownership：拥有 canonical 搜索请求、对象分类、搜索派生读模型、最近搜索、结果编排和搜索反馈的生命周期与写入决定权。
- write boundary：只能通过本领域公开 command 修改其拥有事实。
- 非本域对象：不拥有其他 L1 的事实；跨域协作必须使用对方公开 command、query、projection 或 event。
- 非本域对象：不复制 metadata 中的字段、path、错误码和 wire 语义。

## 3. 上下文边界与协作

- [`JNY-005 / SCN-011`](../spec.md#scn-011) — 在“全局搜索查询与筛选”中，组合各领域公开搜索投影，执行查询、筛选和反馈归因，并返回可导航的搜索结果。
- [`JNY-009 / SCN-017`](../spec.md#scn-017) — 在“内容与页面上下文感知问答”中，组合各领域公开搜索投影，执行查询、筛选和反馈归因，并返回可导航的搜索结果。
- [`JNY-009 / SCN-019`](../spec.md#scn-019) — 在“搜索 handoff 与统一 grounding”中，组合各领域公开搜索投影，执行查询、筛选和反馈归因，并返回可导航的搜索结果。

## 4. 架构与数据流

- [`cross-domain-search`](./cross-domain-search/spec.md)：提供从一级页面进入两段式全屏搜索，并完成最近记录、实时联想、独立网络结果、语音转词与 `小趣搜` 结果查看的完整链路。
- [`search-provider-routing-and-storage-topology`](./search-provider-routing-and-storage-topology/spec.md)：统一搜索 contract、对象 taxonomy、Provider 路由、显式降级、本地搜索生命周期与云侧派生读模型，为全屏搜索和页面内 picker 提供同一查询边界。
- 工程边界由 spec 的“工程归属”声明；设计不复制具体实现文件。

## 5. 关键决策

<a id="dec-001"></a>
### DEC-001 搜索对象按本地、远端与混合 Provider 明确路由
- 决策：搜索对象按本地、远端与混合 Provider 明确路由。
- 理由：统一搜索覆盖联系人、会话、内容、圈子、主页、地点和网络结果，在本地联想与云侧最终结果之间保持清晰合同，并将反馈归因到搜索和推荐。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 关联能力：[`cross-domain-search`](./cross-domain-search/spec.md)、[`search-provider-routing-and-storage-topology`](./search-provider-routing-and-storage-topology/spec.md)

<a id="dec-002"></a>
### DEC-002 中文检索采用 Elasticsearch + IK/pinyin 插件，放弃 OpenSearch 可移植假设
- 决策：统一搜索读库锁定 Elasticsearch 发行版，索引 analyzer 链采用 `analysis-ik`（`ik_max_word` 索引 / `ik_smart` 查询）与 `analysis-pinyin`（仅 title/name 类短字段子字段）；自建含插件的 ES 镜像并 digest pin。
- 理由：内置 `cjk_bigram` 只能提供二元组召回，无语义分词、无拼音、精度不满足商用中文检索；IK 语义分词同时减少 term 数量、降低索引体积。搜索引擎级中文体验的价值高于保留 OpenSearch 可移植性的期权价值。
- 被否决方案：继续使用无插件 `cjk_bigram` 保持 ES/OpenSearch 双兼容；对正文字段启用 edge_ngram 前缀索引（索引体积膨胀约 15-17 倍，成本不可接受）。
- 约束与影响：analyzer 变更无法原地生效，索引必须经 read/write alias 分离的零停机重建流程切换；IK 需保留 `remote_ext_dict` 远程词典热更新入口。ES 镜像升级路径与插件版本必须同步 pin。
- 关联要求：[`search-provider-routing-and-storage-topology`](./search-provider-routing-and-storage-topology/spec.md) 的存储拓扑 REQ。

## 6. 质量与运行约束

- 不设计细粒度灰度，保留整版回滚与观测。
- fallback 结果必须返回 `resolvedFrom=local_fallback` 一类 typed 降级标记，以支撑 UI 和观测。
- 未来若需要统一高性能搜索读库，可替换 read model 的底层实现，但不改变 canonical `search(request)` contract。
- feature flag、观测、SLO 验证与回滚方案。

## 7. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：按 canonical recovery action 重试、刷新或回滚到上一份已验证配置。
- 禁止 fallback：不得使用 Mock、旧 wire、双读双写或跨域直写伪造成功。
