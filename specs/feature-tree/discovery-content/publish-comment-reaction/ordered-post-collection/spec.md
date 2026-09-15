# L3 Story：跨作品有序合集 (`ordered-post-collection`)

> 所属能力：[发布评论互动状态](../spec.md)
>
> Journey / Scenario：[`JNY-004 / SCN-001`](../../../spec.md#scn-001)
>
> 设计归属：[L2 DEC-003](../design.md#dec-003)

## 1. 用户价值

作为作品作者，我希望把不同视频、图片与文章作品编排成有名称和封面的有序合集，让读者按我的编排持续阅读，并且只有我能管理合集。

## 2. 范围与非目标

### In Scope

- 具有独立身份、所有者、名称、封面、可见性与并发版本的跨 Post 有序合集。
- 所有者创建、编辑、添加成员、移除成员、调整顺序与删除合集。
- 通过正式查询读取合集与分页成员，可见计数和分页结果遵守成员当前权限与下架事实。
- 服务公开命令、查询与持久化端口，以及 App 独立合集页的正式契约。

### Out of Scope

- 不把单篇作品的媒体项、视频片段或图片页解释为跨作品合集成员。
- 不改变成员 Post 的所有者、正文、发布状态或可见性，不因加入公开合集扩大成员权限。
- 不自动发布作品、不实现共同编辑、不用端侧缓存或 Alpha 演练状态冒充服务持久化。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 所有者独占的独立合集生命周期

- 合集是独立内容聚合，成员引用独立 Post；视频、图片与文章可以在同一合集内按作者明确顺序排列。
- 只有经认证的合集所有者可创建和修改其合集，所有管理动作均由公开命令执行；非所有者不能靠提交所有者标识获得写权限。
- 重复成员与不合法编排不写入成功事实；并发编辑必须防止静默覆盖，调用方能识别并恢复版本冲突。
- 删除合集只终止合集及其成员关系，不删除或改写成员 Post；持久化失败不能返回成功。

<a id="req-002"></a>
### REQ-002 查询不泄露成员与合集的受限事实

- 合集可见性与成员 Post 当前可见性分别检查；合集可见不等于成员可见。
- 每一页成员和可见计数以同一调用者权限口径计算；私有、受限、下架或已删除成员不得泄露标识、标题、封面或存在数量。
- 过滤发生在分页结果确定之前，保留剩余可见成员的作者编排顺序，不以过滤后的空页错误表示遍历结束。
- 同一分页视图中的合集改版必须可识别，拒绝静默混合不同版本的编排；成员权限变化后重新读取必须立即按新权限过滤。

<a id="req-003"></a>
### REQ-003 正式合集入口与可恢复管理

- 合集详情页消费 metadata 冻结的 page、route 与公开 operations，不以 Post 详情或媒体分集路由代替。
- 读者可继续阅读有权限的成员，作者可进入真实管理流程；权限失效、删除、版本冲突与服务故障显示可恢复终态，不伪造空合集或管理成功。
- Alpha 演练只证明独立客户端交互，不替代真实服务持久化、公开端口与 Provider conformance 证据。

## 4. 契约引用

- 成员事实：[Post](../../../../../quwoquan_service/services/content-service/contracts/content/post/object.yaml)。
- 成员可见切片：[ContentPostDetailSlice](../../../../../quwoquan_service/services/content-service/contracts/content/post/projections/content_post_detail_slice.yaml)。
- [PostCollection 对象](../../../../../quwoquan_service/services/content-service/contracts/content/post_collection/object.yaml)、[命令与查询](../../../../../quwoquan_service/services/content-service/contracts/content/post_collection/operations.yaml)、[权限内分页切片](../../../../../quwoquan_service/services/content-service/contracts/content/post_collection/projections/post_collection_page.yaml)和[错误恢复](../../../../../quwoquan_service/services/content-service/contracts/content/post_collection/errors.yaml)由 content-service authoring。
- App page、surface 与 route 的正式组合登记仍由 `OPEN-002` 阻断，不在规格中另列 wire schema 或路由字符串。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 所有者编排跨作品合集并持久回读

- GIVEN 经认证作者拥有可管理合集且视频、图片和文章 Post 均可作为合法成员。
- WHEN 作者依次创建、编辑、添加、移除、排序及删除合集，并在各次写入后重启服务回读。
- THEN 所有合法动作持久生效，作者顺序、合集信息与版本保持一致，删除不影响成员 Post。
- AND 非所有者、重复成员、并发过期写入与持久化失败不能写出成功事实。

<a id="gwt-002"></a>
### GWT-002 混合权限与下架成员的分页不可泄露

- GIVEN 合集中穿插可见、受限、下架与删除的成员，且可见成员跨越多个分页边界。
- WHEN 不同权限读者分页浏览并在权限或编排发生变化后继续读取。
- THEN 返回成员和可见计数仅反映当前调用者可读的 Post，顺序正确且没有假终页或受限信息泄露。
- AND 编排版本冲突可识别，权限变化后不继续返回已失权成员。

<a id="gwt-003"></a>
### GWT-003 正式合集页完成阅读与管理恢复

- GIVEN 合集的正式 page、route 与 operations 已由 canonical metadata 生成，客户端连接真实服务。
- WHEN 读者打开合集并阅读成员，作者管理合集后遭遇权限失效或版本冲突。
- THEN 读者进入对应独立 Post，作者管理结果与服务回读一致，失败可恢复且不会被表现为成功。

## 6. 依赖

- 上游事实：Post 身份、类型、发布状态及当前可见性由 Post owner 提供；身份来自已认证 Persona。
- 下游结果：独立合集页、作品浏览器合集入口、作者管理入口与 Alpha 契约演练。
- 父级设计：`DEC-001`；合集并发、分页视图与真实持久化边界须先由本能力设计冻结。

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 合集生产装配与端到端权限联程未闭环

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：两条合集 query 的认证、协议、Mongo 与恢复边界具备内部 conformance，按本节点仅将这两条 operation 裁为实现 ready；Save/Delete 不连带提升。公开读取已迁为对象 owned persisted GraphQL，owner 完整视图不泄露失权内容。对象/环境/App/UAT/release 仍缺当前同候选证据，全部保持阻断；仍需正式生成后 exact registry/owner/客户端组合复验，用户设备与真实内容供给权限联程不得由内部 conformance 替代。
- 完成判定：`GWT-001`、`GWT-002` 由真实 local_contract 与 api_integration 证据绑定，合同 verify/codegen 与持久化 conformance 通过。
- 依赖：本能力设计、content-service canonical contracts 和可用的受管非内存 Provider。按已冻结的 operation/对象/发布分轴决定，真实 operation 保持 blocked 直至其自身认证、协议、持久化与恢复运行 conformance 满足；测试私有 ready Source 只验证真实生成器组合，不能进入发布。owner 逐 operation 裁决后正式生成 registry 并重新验证，不能用旧 REST/Mongo 通过替代。owner 管理读取必须消费 UserAccount authority 窄查询委托，不能复用仅匿名的 Post 内部读取或扩大旧 delegated persona compatibility scope。

<a id="open-002"></a>
### OPEN-002 App 合集正式路由、页面与管理接缝尚未接通

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：独立合集页、编辑器与主路由已具备；服务两条 REST 查询已退役，App 两条合集读取消费正式生成的 persisted GraphQL client，Save/Delete 继续 REST，无读取 fallback。仍缺面向作者的可发现创建入口、真实签名 registry 公网 App/API 管理联程与设备 UAT；viewer/Alpha 由其 owner 接线，不能由本地生成、Remote/widget 或内部联程替代正式环境验收。
- 完成判定：`GWT-003` 由 App local_contract、真实 api_integration 与 user_acceptance 直接绑定。
- 依赖：`OPEN-001`、App router 与 viewer owner 的不重叠接线。
