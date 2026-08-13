# L2 Design：发布评论互动状态 (`publish-comment-reaction`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“publish-comment-reaction 能力级 SIT，验证文字/照片发布、图片本地编辑、评论、回复、反应计数、行为上报和端云状态协同”需要 `comment-thread`、`filter-catalog-release`、`image-editing`、`post-create-update`、`reaction-state-counter`、`text-post-commercial-publication` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：publish-comment-reaction 能力级 SIT，验证文字/照片发布、图片本地编辑、评论、回复、反应计数、行为上报和端云状态协同。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`comment-thread`](./comment-thread/spec.md)：Gamma 真机完成打开、评论、返回和二次进入。
- [`filter-catalog-release`](./filter-catalog-release/spec.md)：Mongo 真实引擎 contract 覆盖 digest 幂等、状态机和单 active CAS。
- [`image-editing`](./image-editing/spec.md)：全仓无占位符号；工具确认路径全部经 ImageEditorExportEngine 烘焙。
- [`post-create-update`](./post-create-update/spec.md)：从拍摄得到的图片可进入图片选择器底部缩略条或创作编辑器图片列表，并参与排序、编辑和发布。
- [`reaction-state-counter`](./reaction-state-counter/spec.md)：定义“互动状态状态计数”的可观察主路径、失败语义及父能力交接。
- [`text-post-commercial-publication`](./text-post-commercial-publication/spec.md)：micro 与 article 两种确认结果均有 widget 与 payload 合同证据。

## 3. 端云与数据流

- 上游能力：[`discovery-content`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 仅 published 内容可互动，其他状态进入待恢复终态
- 决策：仅 published 内容可互动，其他状态进入待恢复终态。
- 理由：publish-comment-reaction 能力级 SIT，验证文字/照片发布、图片本地编辑、评论、回复、反应计数、行为上报和端云状态协同。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 影响 Story：[`comment-thread`](./comment-thread/spec.md)、[`filter-catalog-release`](./filter-catalog-release/spec.md)、[`image-editing`](./image-editing/spec.md)、[`post-create-update`](./post-create-update/spec.md)、[`reaction-state-counter`](./reaction-state-counter/spec.md)、[`text-post-commercial-publication`](./text-post-commercial-publication/spec.md)
- 关联验收：`SIT-001`

<a id="dec-002"></a>
### DEC-002 不恢复 Post 级收藏，实体意图统一由「想去」承载

- 决策：`favorited` 已从 reaction 契约退场，不恢复 Post 级收藏；内容表面的意图动作
  统一为实体级「想去」（`wishlist_add/remove` 行为事实 + `GetEntityWishlistState`），
  意图对象是内容锚定的 canonical 实体（`primaryHomepageId`），不是 Post 本身。
- 理由：交集飞轮的意图信号源是 `coWishlistedEntity`（都想去同一实体），Post 级收藏
  没有任何消费闭环（无收藏夹场景、无推荐消费、无交集派生），只会稀释「想去」这个
  唯一意图信号的语义；「稍后再看」类内容收藏在出现真实闭环场景（生产者→消费者→用户价值三点齐备）之前不立项。
- 被否决方案：恢复 `favorited` reaction（无消费方的第二意图轨道）；把想去实现为
  Post 级事实（意图锚点错位，无法聚合到实体供给）。
- 约束与影响：涉及「赞+收藏」的历史规格文案按本决策修正为「赞+想去（有实体锚点时）」；想去按钮只在内容锚定到 `wishlistHomepageTypes` 支持的实体时渲染，不做本地推断。
- 关联要求：`REQ-001`
- 影响 Story：[`reaction-state-counter`](./reaction-state-counter/spec.md)、[`text-post-commercial-publication`](./text-post-commercial-publication/spec.md)
- 关联验收：`SIT-001`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- SLO：列表 P95 800ms / 回复与命令 P95 500ms；hotScore 投影收敛滞后 SLI + 告警。
- 灰度：Canary → 1% → 50% → 100%，回滚条件绑定评论创建成功率与列表可用性 SLO。
