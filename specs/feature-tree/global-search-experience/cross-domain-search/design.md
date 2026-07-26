# L2 Design：跨领域搜索 (`cross-domain-search`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“提供从一级页面进入两段式全屏搜索，并完成最近记录、实时联想、独立网络结果、语音转词与 `小趣搜` 结果查看的完整链路”需要 `circle-facet-search-and-filter`、`full-screen-search-shell-and-entry`、`local-chat-search-contract`、`multi-domain-result-composition`、`recent-search-sync-and-voice-asr`、`search-intersection-consumption`、`xiaoqu-entry-handoff` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：提供从一级页面进入两段式全屏搜索，并完成最近记录、实时联想、独立网络结果、语音转词与 `小趣搜` 结果查看的完整链路。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`circle-facet-search-and-filter`](./circle-facet-search-and-filter/spec.md)：搜索聚合分区使用“讨论”、消息 group 使用“群聊”、Circle 对象使用“圈子”。
- [`full-screen-search-shell-and-entry`](./full-screen-search-shell-and-entry/spec.md)：用户无需输入即可看到继续搜索和产生兴趣的真实启发内容。
- [`local-chat-search-contract`](./local-chat-search-contract/spec.md)：页面与业务层只允许调用 canonical `search(request)`，不得直接依赖聊天域搜索方法名。
- [`multi-domain-result-composition`](./multi-domain-result-composition/spec.md)：输入“钱”可预览并打开发布态“东钱湖”实体主页。
- [`recent-search-sync-and-voice-asr`](./recent-search-sync-and-voice-asr/spec.md)：local_contract 与真实 Mongo api_integration 覆盖相同去重、receipt、owner isolation 行为。
- [`search-intersection-consumption`](./search-intersection-consumption/spec.md)：connected / discovery / intersection_lead 三组互斥，connected 区不展示交集句。
- [`xiaoqu-entry-handoff`](./xiaoqu-entry-handoff/spec.md)：SearchXiaoquResults 不再返回固定 spec/knowledge 占位 citation。

## 3. 端云与数据流

- 上游能力：[`global-search-experience`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 全屏搜索壳组合本地、云端与小趣结果但不复制领域写事实
- 决策：全屏搜索壳组合本地、云端与小趣结果但不复制领域写事实。
- 理由：提供从一级页面进入两段式全屏搜索，并完成最近记录、实时联想、独立网络结果、语音转词与 `小趣搜` 结果查看的完整链路。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 影响 Story：[`circle-facet-search-and-filter`](./circle-facet-search-and-filter/spec.md)、[`full-screen-search-shell-and-entry`](./full-screen-search-shell-and-entry/spec.md)、[`local-chat-search-contract`](./local-chat-search-contract/spec.md)、[`multi-domain-result-composition`](./multi-domain-result-composition/spec.md)、[`recent-search-sync-and-voice-asr`](./recent-search-sync-and-voice-asr/spec.md)、[`search-intersection-consumption`](./search-intersection-consumption/spec.md)、[`xiaoqu-entry-handoff`](./xiaoqu-entry-handoff/spec.md)
- 关联验收：`SIT-001`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 发布策略按整版上线，观测与回滚前置。
- feature flag、观测、SLO 验证与回滚方案。
