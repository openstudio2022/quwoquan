# L3 Story：统一呈现模型 (`unified-presentation-model`)

> 所属能力：[`content-type-framework`](../spec.md)
>
> Journey / Scenario：[`JNY-004 / SCN-001`](../../../spec.md#scn-001)
>
> 设计引用：[L2 DEC-004](../design.md#dec-004)、[L2 DEC-005](../design.md#dec-005)

## 1. 用户价值

作为浏览或创作内容的用户，
我希望同一内容在首页、作者主页、沉浸浏览和分享中保持对象、正文、媒体与互动事实一致，
从而不因入口或附件变化被误认为另一种内容。

## 2. 范围与非目标

### In Scope

- 图片、视频、文章三类 Post 的单一只读投影及跨面消费。
- 文章的纯文字与富文图文混排、图片的有配文与无配文展示。
- 实体主页与 Post 的投影边界、缺失与未知值的可观察失败。

### Out of Scope

- 发布写链路与存量迁移的执行；对象、Surface、布局与首页可选 recipe 的定义由父能力拥有。
- 新卡片视觉、新的 Surface 或旧投影兼容通道。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 同一对象跨面保持同源事实

- 三类 Post 共用权威对象事实；标题、作者、正文、媒体顺序与互动状态不得由各页面重新拼装成相互矛盾的副本。
- 文章允许纯文字与富文图文混排；增加或移除正文插图不改变文章类型。图片允许有或无短配文，图片集合与配文分区呈现，不成为可插入正文段落的图文混排文章。
- 实体主页保持独立对象，不能伪装成 Post；对象选择、内容筛选、卡片家族、导航各自消费父能力规定的单一权威字段。

<a id="req-002"></a>
### REQ-002 页面差异不改变内容身份

- 首页和作者主页遵循各自 Surface 布局，聚焦面保持全屏；列数不由类型、媒体数量或 recipe 推导。
- 首页可选 recipe 只服务首页卡片家族，作者主页与聚焦面不消费该配方。
- 点击只按云物化的目的面导航；文章正文图片的浏览层不是新 Post，也不改变文章目的面。

<a id="req-003"></a>
### REQ-003 缺失与未知值不触发旧投影兜底

- 禁止从媒体附件嗅探类型或目的面，禁止恢复 `identity`、`displayFormat`、`isArticleLike` 派生轴。
- 统一投影是唯一生产读取路径；不保留旧投影并行兜底、双读开关或分享模板内补猜。
- 未知列表项按父能力契约逐项隔离并观测，其他已知项仍可浏览；深链未知能力进入需升级的 typed 终态，不误报删除、不默认画成文章或封面卡。

## 4. 契约引用

- canonical：`quwoquan_service/contracts/metadata/_shared/types.yaml#ContentType`
- canonical：`quwoquan_service/contracts/metadata/_shared/types.yaml#ListItemPresentationEnvelope`
- canonical：`quwoquan_service/services/content-service/contracts/content/post/projections/post_read_presentation.yaml#PostReadPresentation`
- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 三类 Post 的正文与媒体事实跨面一致

- GIVEN 同一作者发布纯文字文章、段落与图片交错的文章、有配文图片、无配文图片及视频，且均可见。
- WHEN 用户从首页打开内容、返回并从作者主页再次打开，再发起分享。
- THEN 各入口读取同一对象身份、作者、正文与媒体顺序；两种文章始终为文章，两种图片始终为图片且配文不插入图片序列。
- AND 任一文章增减插图或任一图片增减配文后，读侧不改写类型、不新增身份或展示形态派生值。

<a id="gwt-002"></a>
### GWT-002 Surface 与对象身份正交

- GIVEN 同一 Post 出现在首页和作者主页，首页还包含一项独立实体主页。
- WHEN 用户切换 compact 与 expanded 视口并分别点击各项。
- THEN 首页与作者主页按各自布局策略改变列数，Post 身份不变；卡片点击抵达云声明的目的面，实体主页只打开实体主页详情。
- AND 作者主页和聚焦面不依赖首页 recipe；文章、媒体聚焦面保持各自全屏语义。

<a id="gwt-003"></a>
### GWT-003 未知或缺失展示信息不污染已知项

- GIVEN 同一列表的已知项之间分别插入未知对象种类、内容类型、首页配方、目的面或必需展示信息缺失的项，异常项仍附带可解码媒体；另有深链指向不支持的目的面。
- WHEN 客户端逐项解码、展示并续页，然后打开该深链。
- THEN 仅异常项被隔离并产生 canonical 契约偏差观测，前后已知项保持服务端序位与可点击性；解码异常不逃逸为整页失败，不按附件补猜或回退旧投影，也不为未知对象种类强解 Post 投影。
- AND 深链显示需升级的 typed 终态并允许返回，不显示默认内容卡或“内容已删除”。
- AND 隔离不改变服务端 cursor 或已交付序位，不在端侧合成替补对象、把该页的全部项均被隔离等同于候选耗尽，或发起无界补页。

## 6. 依赖

- 前置要求：[`content-type-framework`](../spec.md) 的四轴与能力协商要求。
- 布局与跨面状态：[`content-display-consistency`](../../content-display-consistency/spec.md)。
- 父级设计：[L2 DEC-004](../design.md#dec-004)、[L2 DEC-005](../design.md#dec-005)。

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 统一投影跨面行为与未知值隔离证据

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：三类内容的代码调整不证明四轴已经贯通；尚缺匹配当前正文形式、布局导航和未知项隔离要求的真实测试，静态门禁通过不能替代用户行为验收。
- 完成判定：`GWT-001`、`GWT-002`、`GWT-003` 由真实 `local_contract`、`api_integration` 与 `user_acceptance` 分层绑定，端侧生成闭集与请求边界按父能力 OPEN 完成，不存在旧投影兜底。
