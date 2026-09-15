# L3 Story：作品关联的类型化摘要 (`typed-post-associations`)

> 所属能力：[发布评论互动状态](../spec.md)
>
> Journey / Scenario：[`JNY-004 / SCN-001`](../../../spec.md#scn-001)
>
> 设计归属：[L2 DEC-004](../design.md#dec-004)

## 1. 用户价值

作为作品读者，我希望清楚区分作品涉及的话题、新闻事件、真实地点与作者参与活动，并通过真实关联进入正确对象，而不被相似展示文案误导。

## 2. 范围与非目标

### In Scope

- Post 读侧向展示层交付权限过滤后的类型化关联摘要。
- 话题与新闻事件沿 canonical 标签事实表达；地点引用真实 Homepage；参与活动沿独立 Gathering 参与事实表达。
- 为后续作品浏览器两行关联展示提供明确类型与目标身份，不由页面推测关联种类。

### Out of Scope

- 不创建标签、地点或 Gathering 的第二真相源，不根据标题、地名、URL 或展示文案猜测 canonical 引用。
- 不把新闻事件当作参与活动，不把普通地点文本当作可导航主页。
- 不在本故事实现浏览器布局、全局样式或活动参与命令。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 关联种类遵守真实对象所有权

- 话题与新闻事件只来自已发布且可解析的 canonical 标签，保留可区分的关联类型。
- 地点只在存在可访问的真实 Homepage 时提供主页导航；纯文本地点不冒充主页身份。
- Gathering 关联只表达作者具有有效参与事实的活动，不能从新闻事件标签、作品来源或地点相同推导出参与。
- 所有摘要保留目标 owner 的事实边界；Post 不复制或改写标签、Homepage 与 Gathering 的生命周期。

<a id="req-002"></a>
### REQ-002 读侧投影显式且不可伪造

- 展示层消费 typed summary，不通过标题前缀、字符串拼接、PostMediaItem 或不透明通用映射推断对象类型。
- 未发布、悬空、失权或不可访问关联不能产生可点击的成功摘要，缺少真实事实时不生成占位关联。
- 关联过滤与目标导航使用一致的当前可见性口径；上游故障不能被缓存旧成功或假空结果掩盖。
- 合集摘要只来自独立合集 owner，不以单 Post 的媒体项伪造跨作品关系。

## 4. 契约引用

- [Post fields 与语义关联事实](../../../../../quwoquan_service/services/content-service/contracts/content/post/fields.yaml)。
- [Post 只读详情切片](../../../../../quwoquan_service/services/content-service/contracts/content/post/projections/content_post_detail_slice.yaml)。
- typed summary 的 authoring owner 为 Post projection，canonical 标签、Homepage 与 Gathering 事实仍归各自对象；新增投影合同尚待 `OPEN-001` 冻结。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 四类关联不混淆身份

- GIVEN Post 具有已发布话题与新闻事件标签、可访问真实地点主页及作者有效参与的 Gathering。
- WHEN 读侧解析并交付关联摘要。
- THEN 摘要保留各类 canonical 身份与不同类型，地点导航指向真实主页，参与活动不与新闻事件混淆。

<a id="gwt-002"></a>
### GWT-002 不完整或失效关联不伪造入口

- GIVEN 关联包含纯文本地点、悬空标签、已下架目标、无参与证明活动或上游读取失败。
- WHEN 读侧解析关联或权限变化后重新读取。
- THEN 无法证明的关联不产生成功导航入口，依赖故障可识别且不被伪造为空或旧成功。

<a id="gwt-003"></a>
### GWT-003 合集摘要与单作品媒体保持区分

- GIVEN 一篇含多个媒体项的 Post 以及独立 owner 建立的跨 Post 合集。
- WHEN 读侧提供作品关联摘要。
- THEN 只有真实独立合集关系形成合集摘要，媒体项数量或顺序不会被解释为合集。

## 6. 依赖

- 上游事实：canonical 标签、Homepage 可见性、Gathering Participation、Post published semantic mentions。
- 下游结果：作品浏览器两行关联布局与 typed 导航适配。
- 父级设计：`DEC-001`；跨对象读取、故障与权限过滤策略须在能力设计冻结。

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 typed 关联合同与真实投影生产链尚未建立

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：关联类型、摘要合同与 fail-closed projector 规则已具备；尚缺各 owning reader 的真实解析装配、详情响应挂载和 App summary ABI 消费。Content 配置没有 Homepage 服务读取依赖，现有标签桥接 reader 为推荐容错用途，不能拿它的 fail-open 缓存承担当前关联权限；缺少这些依赖时不产生成功摘要，页面不能自行猜测身份。
- 完成判定：`GWT-001`、`GWT-002`、`GWT-003` 由投影 local_contract 与真实对象读取 api_integration 直接绑定，Service/App 生成合同通过。
- 依赖：Post projection authoring、标签/实体/活动公开读取端口、独立合集 owner 和 viewer 接线。
