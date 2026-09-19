# L2 Design：内容类型框架 (`content-type-framework`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“content_feed 场景下对象身份、展示面、面布局与可选配方四层互不推导；`ContentType` 三类（图片 image、视频 video、文章 article）共用通用内容模型与按类型扩展的约定，不拆表、不拆场景；实体主页不入库为 Post”需要 `creation-mode-and-surface-ia-unification`、`creation-tagging-ia`、`markdown-article-kernel`、`unified-presentation-model` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：content_feed 场景下对三种内容类型（图片 image、视频 video、文章 article）的通用内容模型与按类型扩展的约定，不拆表、不拆场景；实体主页不入库为 Post。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`creation-mode-and-surface-ia-unification`](./creation-mode-and-surface-ia-unification/spec.md)：用户只需要在入口选择开始动作，系统能根据真实媒体结果进入图片或视频编辑状态，且发布 payload 的 `contentType` 与最终媒体类型一致。
- [`creation-tagging-ia`](./creation-tagging-ia/spec.md)：各类型编辑页提供可选标签，未选择标签不得阻断发布。
- [`markdown-article-kernel`](./markdown-article-kernel/spec.md)：小屏或可访问性大字号下统一降级为 `fullWidth`。
- [`unified-presentation-model`](./unified-presentation-model/spec.md)：单一只读投影保持三类 Post 跨面事实一致，未知项隔离且不保留旧投影兜底。

## 3. 端云与数据流

- 上游能力：[`discovery-content`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 三类 Post 共用生命周期；实体主页不入库为 Post
- 决策：`ContentType` 三类（`image`、`video`、`article`）共用 Post 生命周期并按 contentType 扩展策略；实体主页保持 `entity.homepage`，不进入 Post 表。退役整个 `ContentIdentity`（`moment`/`work`）与 `PromotePostToWork`。
- 理由：content_feed 场景下对三种内容形式的通用内容模型与按类型扩展的约定，不拆表、不拆场景。`ContentIdentity` 混淆了内容形式与展示面，已由 `ContentUiSurface` 替代。
- 被否决方案：保留 `ContentType.micro`；`ContentIdentity` 作为兼容层；把实体主页存为特殊 Post；由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。存量 `contentType=micro` 在一次性迁移中分类为 `image`/`video`/`article`，冲突或无法分类的 typed fail-closed 不进公开 feed。
- 关联要求：`REQ-001`
- 影响 Story：[`creation-mode-and-surface-ia-unification`](./creation-mode-and-surface-ia-unification/spec.md)、[`creation-tagging-ia`](./creation-tagging-ia/spec.md)、[`markdown-article-kernel`](./markdown-article-kernel/spec.md)、[`unified-presentation-model`](./unified-presentation-model/spec.md)
- 关联验收：`SIT-001`、`SIT-003`

<a id="dec-002"></a>
### DEC-002 创作工作台壳层使用 CupertinoPageScaffold 而非 AppScaffold

- 决策：`CreatePage`（`content.create`）壳层保留 `CupertinoPageScaffold` + 页面内自建透明
  `Material` ancestor，不收敛到 `AppScaffold`。
- 理由：创作工作台是 iOS 原生沉浸编辑面（全屏编辑器、键盘联动工具条、Cupertino 导航语义），`CupertinoPageScaffold` 是 iOS 语义 v1 的正确基座；`AppScaffold` 面向常规内容页的
  统一 chrome（顶栏/背景/安全区约定），对编辑器场景反而引入多余层级。页面横向质量矩阵
  对壳层的要求以「语义 token + 双模式 + 安全区正确」为准，不强制单一 Widget 基座。
- 被否决方案：把 `CreatePage` 包进 `AppScaffold`（多余 chrome 层且破坏编辑器沉浸布局）；为编辑器新建第三种页面壳（违反材质单层单义与壳层单轨）。
- 约束与影响：`CreatePage` 及其 embedded 子页（排版预览、选圈、选位置）继续满足
  design token、双模式、44×44 热区与 i18n 约束；透明 Material ancestor 只允许由
  `CreatePage` 壳层提供一次，子组件不得再自建。
- 关联要求：`REQ-001`
- 影响 Story：[`creation-mode-and-surface-ia-unification`](./creation-mode-and-surface-ia-unification/spec.md)
- 关联验收：`SIT-001`

<a id="dec-003"></a>
### DEC-003 semantic document 是跨端正文与布局意图的唯一协议

- 决策：article 的 canonical 输出是单一 semantic document；Markdown 与 HTML 是显式 mapping type，统一映射到稳定节点身份和节点闭集，Web/Android/iOS/工作台只消费同一节点树。语法原文、端组件树和 renderer 输出均不是第二正文 authority。
- 协议版本边界：semantic protocol 以 `(schemaVersion, dialectVersion, canonicalizationVersion)` version triplet 分别版本化 AST envelope/字段、Markdown grammar 与节点映射、canonical bytes/digest。reader 先校验 triplet 与 required capabilities；unknown schema/dialect major、canonicalization mismatch 或 capability missing typed fail closed。minor compatibility 只能按 canonical contract 明示，禁止以 best-effort renderer 或字段忽略自行扩兼容。
- 对象版本边界：对象另以 `(contentRevision, sourceRevision, layoutRevision)` exact tuple 标识可重放事实。content 拥有作者表达，source 拥有采用证据的 exact revision，layout 拥有同一节点树的一套统一响应式/可访问布局规则；三个维度分别推进、create-once，reader 必须读取一个已存在 tuple，不允许 latest-by-dimension 拼装。protocol triplet 与 object tuple 正交且必须同时绑定，均不得替代另一组。
- 表格与布局：mapper 一次性判定 `data table|layout table`。data table 保留 row/column/header/caption/cell reading order 并跨端使用同一响应式规则；layout table 按受治理顺序线性化且不暴露数据表语义。视口断点只能应用同一 `layoutRevision` 声明的尺寸、换行、滚动或线性化规则，不能选择不同节点、内容结构、阅读顺序或分类。
- 失败与人工恢复：未知/有损映射、版本缺失或 tuple 漂移返回可定位 node/source 的 typed disposition；自动流程不得猜测。人工可选择修订、替换来源、显式接受受治理降级或放弃，但决定必须由 producer/review owner 形成新 revision 并重新审核，工作台仅展示 diagnostic 与收集离线建议。
- 被否决方案：每端持有 Markdown/HTML 副本、移动端模板、有据整理后覆盖来源表达、按 renderer 推断表格类型、三个 latest revision 临时拼接、工作台修补 canonical AST。
- 可测试面：mapper golden/local_contract 锁定节点身份、两类 mapping、protocol triplet 与表格分类；对象 tuple 并发/漂移测试锁定三维 revision 独立性，协议负例锁定 unknown schema/dialect major、canonicalization mismatch 与 required capability missing；跨端 fixture 在多 viewport 逐节点比对结构、语义、阅读顺序与可访问表头，工作台写入 canonical root 必须失败。
- 关联要求：[`markdown-article-kernel REQ-006`](./markdown-article-kernel/spec.md#req-006)
- 影响 Story：[`markdown-article-kernel`](./markdown-article-kernel/spec.md)
- 关联验收：[`GWT-005`](./markdown-article-kernel/spec.md#gwt-005)

<a id="dec-004"></a>
### DEC-004 每个展示与跳转语义只占一个出站字段，端侧禁止多字段交叉推导

- 决策：列表信封里 `objectKind` 选投影、`contentType` 做筛选与媒体槽、`presentationRecipe` 选首页卡、`openSurface` 决定点击去向，四个字段各自是该语义的唯一可写载体，端一次只读一个字段做一件事。禁止用取值组合推出未声明的第三概念，禁止从 `mediaUrls` / `videoUrl` 嗅探展示形态；`displayFormat`、`identity`、`isArticleLike` 三条读侧派生轴随本决策删除。
- 理由：现有债务的共同形状是多个字段取值交叉发明一个从未声明的概念（`micro` × 有无媒体附件推出 `displayFormat`，`work` × `note` 推出 `isArticleLike`，埋点再把 identity 当成 contentType 上报），读侧因此变成第二真相源。[`runtime DEC-030`](../../runtime/system-architecture-and-engineering-guide/design.md#dec-030) 要求闭集在每条消费管线上类型化、读侧不得发明取值，一个业务语义只能有一个可写载体。
- 被否决方案：保留 `displayFormat` 作为展示形态的第二载体；让端继续按 `contentType` 加媒体附件推断卡片；先把字符串换成常量再开 typed enum；把侵入式浏览器编码成一种内容类型或一个 `displayFormat` 取值。
- 约束与影响：每个字段有独立闭集与独立 owner，新增语义只能新增字段或扩展该字段闭集，不得复用既有字段的取值组合。端侧按单字段登记表分派，闭集缺成员必须编译失败而不是落默认分支；埋点维度与字段一一对应，identity 不得冒充 contentType。
- 关联要求：[`REQ-001`](./spec.md#req-001)、[`REQ-005`](./spec.md#req-005)、[`REQ-007`](./spec.md#req-007)
- 影响 Story：[`unified-presentation-model`](./unified-presentation-model/spec.md)、[`creation-mode-and-surface-ia-unification`](./creation-mode-and-surface-ia-unification/spec.md)
- 关联验收：[`SIT-001`](./spec.md#sit-001)、[`SIT-003`](./spec.md#sit-003)

<a id="dec-005"></a>
### DEC-005 openSurface 与 presentationRecipe 由云按契约赋值表物化，赋值表不下发到 App

- 决策：契约里的目的面赋值表与 recipe 赋值规则只存在于 contracts 与云侧，服务端在出站投影时把结果写成单字段 `openSurface` / `presentationRecipe`。App 不持有赋值表，也不按 `contentType` 加 `objectKind` 重算目的面；wire 未写明这两个字段时端侧按 typed 失败处理，没有媒体嗅探或默认卡片的恢复通道。
- 理由：赋值表是一次服务端投影，不是端侧算法；下发到 App 等于让同一规则在两侧各算一遍并立即漂移。按「云拥有对象事实与出站赋值、端拥有编译期闭集与渲染」切开后，新增目的面或卡片家族只改契约与云侧，旧包无需理解新规则也不会解码失败。
- 被否决方案：把赋值表随远端配置或 ui_config 下发到 App 再算一遍；用 `X-Client-App-Build` 维护第二张版本到能力的映射表；端侧字段缺失时回退到封面卡或按媒体推断；把 GraphQL 详情切片的 `supportedContentTypes` 当成客户端能力广告复用。
- 约束与影响：`openSurface` 是每个列表项的必填字段，`presentationRecipe` 只在 `homeFeed` 的项上出现；content hydration 不得改写 recommendation 已写入的赋值，也不得按媒体补全缺失值。未知或缺失取值一律 fail-closed（列表项丢弃、深链返回 typed 升级终态），不存在把未知值画成某种默认展示的通道。
- 能力边界：请求整份能力声明缺席时服务使用契约显式固定并生成的最小集合；非法声明或摘要不匹配不得采用默认。最小集合成员来自契约下可真实支持的基线，不从最新枚举自动求全量；App 仍必须发送生成能力。摘要校验、窗口隔离和有界补页的单一设计由 [feed DEC-006](../feed-orchestration-recommendation/design.md#dec-006) 拥有，单项隔离不能反向改写这些事实。
- 关联要求：[`REQ-002`](./spec.md#req-002)、[`REQ-004`](./spec.md#req-004)、[`REQ-006`](./spec.md#req-006)
- 影响 Story：[`unified-presentation-model`](./unified-presentation-model/spec.md)
- 关联验收：[`SIT-001`](./spec.md#sit-001)、[`SIT-002`](./spec.md#sit-002)

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 引擎已按 ContentType 做 maxPerType；运营可配置「各类型占比/上下限」，由通用 pipeline 读取配置并按 contentType 执行。
- 按 contentType 配置不同规则（如视频先审、文章敏感词+人工抽检）。
- 运营配置「content_feed 各类型占比/上下限」，引擎多样性层已具备 typeCount，将配置与 maxPerType 等参数打通。
- 「仅视频专区」「仅文章专题」等在编排层或 feed 配置中按 contentType 过滤/加权即可。
