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
- 约束与影响：涉及「赞+收藏」的历史规格文案按本决策修正为「赞+想去（有实体锚点时）」；works 沉浸页的想去按钮只在内容锚定到 `wishlistHomepageTypes` 支持的实体时渲染，不做本地推断。首页内容 Post 卡不消费该动作，即使携带合法锚点也不渲染想去 UI、语义或登录续接；实体主页入口、实体 wishlist contracts 与 `coWishlistedEntity` 派生保持不变。
- 关联要求：`REQ-001`
- 影响 Story：[`reaction-state-counter`](./reaction-state-counter/spec.md)、[`text-post-commercial-publication`](./text-post-commercial-publication/spec.md)
- 关联验收：`SIT-001`

<a id="dec-003"></a>
### DEC-003 合集独立聚合与权限内分页

- 决策：PostCollection 独占合集元信息和有序 Post 引用，所有者命令以预期版本作 Mongo 单文档 CAS；创建使用调用者提供的稳定合集身份，重试不得重建第二合集。删除采用墓碑状态，保留版本以拒绝旧命令。Post 内容与可见性不复制到合集存储。
- 理由：跨作品顺序、所有权与并发版本构成独立一致性边界；单 Post 媒体项不能表达合集，也不能承载跨作品权限。
- 被否决方案：PostMediaItem 分集、页面内存合集、跨对象直接读写私有 Mongo 集合、无版本覆盖保存与客户端过滤分页。
- 约束与影响：合集 named reader 经 Post 公开 reader 查询当前可见成员，在保留作者顺序后对可见结果分页、计数；游标绑定合集身份、调用者和版本及最后扫描位置，编排变更拒绝续页，权限收缩每次重新过滤，不让失权成员与数量泄露。依赖读取失败传播 typed failure，不能伪造成空集合。
- 命令与查询：公开 Facade 独占创建、修改与删除；成员增删和排序在同一次预期版本替换中原子生效。公共查询只输出调用者可见成员及计数，不能作为聚合写回。独立 owner 管理 reader 返回已拥有的完整编排引用，失权成员不附带标题、媒体、类型或下架原因；客户端只从该视图编辑。新增成员与封面由现役作者作品 typed 查询选择，不提供内部标识符文本输入。公开 HTTP、App page 与 route 必须来自对象 metadata；在正式接线与 conformance 完成前保留 Story block OPEN。
- 一致性与幂等：同版本同状态重复命令回读原结果；过期且内容不同的请求返回版本冲突，不自动覆盖；数据库不确定失败由调用者先回读，不伪造成功回执。读取无跨对象事务保证，每次查询基于当前 Post 权限，后续导航仍由 Post 再鉴权。
- 恢复与回滚：版本冲突刷新后由作者重新确认；缺失或失权合集同为不可访问；存储或上游失败可重试读取，删除不触碰成员 Post。回滚停用合集入口与新写操作，保留 Mongo 数据和墓碑，禁止回退到本地第二真相源。
- SLI/SLO：命令及查询成功率、依赖失败率、CAS 冲突率与 P95 延迟；查询沿用本能力 800ms、命令 500ms 预算，持续超预算或存储失败触发停止放量。trace/request identity 由边界继承，只记录 outcome 与计数，不记录标题、成员标识及 cursor 原文。
- 测试 seam：固定身份与时钟的 Facade local_contract、真实 Mongo CAS/重启回读 conformance、Post named reader 权限分页 contract；App 单独证明 generated Remote/typed port，真实环境证据缺失不得视为可发布。
- 关联要求：`ordered-post-collection` 的 `REQ-001`、`REQ-002`、`REQ-003`。
- 影响 Story：[`ordered-post-collection`](./ordered-post-collection/spec.md)。
- 关联验收：`ordered-post-collection` 的 `GWT-001`、`GWT-002`、`GWT-003`。

<a id="dec-004"></a>
### DEC-004 Post 关联摘要只解析 canonical 引用

- 决策：Post named projection reader 通过各 owner 的公开查询将已发布 semantic mention、真实 Homepage、具有 Participation 的 Gathering 和独立合集引用解析成闭集 typed summary；目标类型显式区分话题、新闻事件、地点、参与活动和合集。
- 理由：关联标签与活动参与、地点文本与真实主页具有不同事实来源，字符串相似不是关系证据。
- 被否决方案：根据标题或 URL 猜对象、把新闻标签当活动、从同地点推断参与以及复制其他对象完整状态。
- 约束与影响：所有目标在响应前验证可见与有效性；不存在或无权限的引用不产生成功入口，上游读取失败向调用者传播而不回退旧摘要。页面消费 typed summary，布局与导航接线不改变事实所有权。
- 恢复与回滚：上游故障按 read failure 重试；错误映射修复后重新读取，禁止旧 wire 双读或默认成功。停止投放关联入口不删除 canonical 来源事实。
- 质量与观测：摘要共享详情读取预算，记录依赖类别与 outcome，禁止输出引用标识或原文；P95 或失败率持续越过详情预算时停止放量。不同 owner reader 的 typed seam 用于检验失权、悬空与依赖失败，真实跨服务验收保持独立 OPEN。
- 关联要求：`typed-post-associations` 的 `REQ-001`、`REQ-002`。
- 影响 Story：[`typed-post-associations`](./typed-post-associations/spec.md)。
- 关联验收：`typed-post-associations` 的 `GWT-001`、`GWT-002`、`GWT-003`。

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- SLO：列表 P95 800ms / 回复与命令 P95 500ms；hotScore 投影收敛滞后 SLI + 告警。
- 灰度：Canary → 1% → 50% → 100%，回滚条件绑定评论创建成功率与列表可用性 SLO。
