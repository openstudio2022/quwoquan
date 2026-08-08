# L3 Story：圈子主页与群组详情模板 (`circle-homepage-redesign`)

> 所属能力：[`circle-experience-redesign`](../spec.md)

> Journey / Scenario：[`JNY-008 / SCN-014`](../../../spec.md#scn-014)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为浏览或参与圈子的用户，
我希望以一次稳定加载查看圈子信息、成员、内容与协作入口，并在分页和刷新后保持状态一致，
从而快速理解圈子并继续加入或参与。

## 2. 范围与非目标

### In Scope

- “圈子主页与群组详情模板”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 圈子主页与群组详情模板

- 单请求、强类型投影、游标增量和缓存收敛合同均有稳定 case ID。

<a id="req-002"></a>
### REQ-002 圈子频道单请求、游标与强类型内容投影

- 单请求、强类型投影、游标增量和缓存收敛合同均有稳定 case ID。

<a id="req-003"></a>
### REQ-003 所有群组详情页共享统一头部信息区：名称、简介、类型徽章、成员数、内容数、群数或节点数

- 所有群组详情页共享统一头部信息区：名称、简介、类型徽章、成员数、内容数、群数或节点数。
- 所有首页模块都必须独立加载和独立降级，单模块失败不影响其他模块使用。
- 详情页层的统一动作叫 `发布内容`。
- `口碑` 必须绑定 1 个主具体事物；`笔记 / 作品 / 提问` 可绑定也可不绑定。
- 内容流采用稳定 keyset cursor。端侧保存 `nextCursor` 并追加服务端顺序，不得重新排序、通过本地成员集合切分 scope，或以 `listCircles → getCircleFeed` 进行 N+1 补造。
- `CircleFeedItemView` 必含 `placementId`，并以显式强类型字段承载帖子、作者、媒体与展示位状态；页面不得将 `Post` 序列化为动态 Map 再恢复展示模型。
- 全局入口层必须使用 `群组` 作为用户词。
- 组织型详情页必须尊重学校、院系、班级、公司、部门等正式组织语义。
- 公开内容主分发面必须在群组层；群层以交流、资料、公告为主。
- 群组详情页的模板差异主要体现在第三个页签和首页模块权重，不得分裂为两套完全不同的产品。

## 4. 契约引用

- canonical：`quwoquan_service/services/circle-service/contracts/circle_management/circle/ui_config.yaml`
- canonical：`quwoquan_service/services/circle-service/contracts/circle_management/circle/operations.yaml`
- canonical：`quwoquan_service/services/circle-service/contracts/circle_management/circle/fields.yaml`
- canonical：`quwoquan_service/services/circle-service/contracts/circle_management/circle/projections/circle_discovery_feed.yaml`
- canonical：`quwoquan_service/services/circle-service/contracts/circle_management/circle/storage.yaml`
- canonical：`quwoquan_service/services/circle-service/contracts/circle_management/circle_group/operations.yaml`
- canonical：`quwoquan_service/services/circle-service/contracts/circle_management/circle_group/fields.yaml`
- canonical：`quwoquan_service/services/circle-service/contracts/circle_management/circle_post_placement/operations.yaml`
- canonical：`quwoquan_service/services/circle-service/contracts/circle_management/circle_post_placement/fields.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 圈子主页与群组详情模板

- GIVEN 圈子成员或圈子运营者具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“圈子主页与群组详情模板”对应的公开行为。
- THEN 单请求、强类型投影、游标增量和缓存收敛合同均有稳定 case ID。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

<a id="gwt-002"></a>
### GWT-002 圈子频道单请求、游标与强类型内容投影

- GIVEN 用户进入有多页内容的圈子频道。
- WHEN 首次加载、继续加载或刷新频道。
- THEN 页面只消费强类型单请求投影，按服务端游标追加并以同一内容事实收敛缓存。

以下 operation 级 GWT 只裁定 CircleGroup owner 的 query/command 终态；它们不替代本 Story 对页面模块、分页追加、缓存收敛与恢复面的组合验收。

<a id="gwt-003"></a>
### GWT-003 分页读取 CircleGroup

- GIVEN 调用 Persona 是 active Circle member，且目标 Circle 至少存在一个符合筛选条件的 CircleGroup。
- WHEN Persona 提交 canonical `ListCircleGroups` 并沿 owner cursor 继续分页。
- THEN 每页返回 nonempty typed `CircleGroupPageSlice`，其中 CircleGroup identity、version、层级、类型、可见性、加入策略与状态来自 owner reader，且不暴露 storage identity 或可写派生字段。
- THEN groupType、visibility、parentGroupId、nodeType 筛选和下一页 cursor 均由 owner reader 裁定，分页保持稳定顺序且不重复、不漏项。
- THEN BOLA、非法 cursor 或 owner reader 失败返回 canonical typed failure，不泄露群组数据，也不把依赖失败合成为成功空页。

<a id="gwt-004"></a>
### GWT-004 搜索 CircleGroup

- GIVEN 调用 Persona 是 active Circle member，且目标 Circle 至少存在一个符合查询与可见性条件的 CircleGroup。
- WHEN Persona 提交 canonical `SearchCircleGroups` 并沿 owner cursor 继续搜索分页。
- THEN 每页返回 nonempty typed `CircleGroupPageSlice`，命中项的 identity、version、name、groupType、visibility 与 status 和 owner authoritative readback 一致。
- THEN query、visibility、groupType 与 cursor 由 owner reader 统一解释，搜索分页保持稳定顺序且不重复、不漏项，不由 App 本地重排或补造结果。
- THEN BOLA、非法 query/cursor 或 owner reader 失败返回 canonical typed failure，不泄露不可见群组，也不合成成功空页。

<a id="gwt-005"></a>
### GWT-005 读取单个 CircleGroup

- GIVEN 调用 Persona 有权读取目标 CircleGroup，且该聚合存在。
- WHEN Persona 提交 canonical `GetCircleGroup`。
- THEN 返回 nonempty typed `CircleGroupSlice`，其 identity、version、circle、parent、类型、策略、conversation binding 与 lifecycle 状态和 owner authoritative readback 一致，且不暴露 storage identity。
- THEN 查询身份固定为认证 Persona 与 path 中的 Circle/CircleGroup，调用方不能通过 query、payload 或相邻 Circle identity 绕过 owner BOLA。
- THEN group 不存在、身份不匹配、无权读取或 owner reader 失败返回对应 canonical typed failure，不把依赖失败合成为不存在或空成功态。

<a id="gwt-006"></a>
### GWT-006 更新 CircleGroup

- GIVEN 调用 Persona 是目标 CircleGroup owner 或 manager，expected version、父层级与可变策略均有效。
- WHEN Persona 使用稳定幂等键提交 canonical `UpdateCircleGroup`。
- THEN command receipt 与 fresh `GetCircleGroup` authoritative readback 收敛到同一 group identity、新 version 与更新后的可变策略，且只提交一次状态变化与 outbox。
- THEN 相同幂等键重放同一语义命令返回同一 group 与 receipt 身份，不重复推进 version 或 outbox。
- THEN BOLA、归档状态、父层级、version 或幂等冲突返回 canonical typed failure，owner state、receipt 与 outbox 不产生部分成功。

以下 operation 级 GWT 只裁定 CirclePostPlacement owner 的 command 与 named reader 终态；Circle feed、discovery feed、Content Post 或 Recommendation 投影均为下游可重建结果，不得充当 owner authoritative readback。

<a id="gwt-007"></a>
### GWT-007 创建 CirclePostPlacement

- GIVEN 调用 Persona 是 Post owner 或目标 Circle moderator，Post 可被放置，且可选 CircleGroup 确实属于同一 Circle。
- WHEN Persona 使用稳定幂等键提交 canonical `PlacePostInCircle`，随后通过 owner named reader 读取目标 placement。
- THEN command receipt 与 fresh nonempty typed `CirclePostPlacementSlice` authoritative readback 收敛到同一 placement identity、version、Circle、可选 CircleGroup、Post、owner 与 `active` 状态，且只提交一次 owner state、receipt 与 outbox。
- THEN 相同幂等键重放同一语义命令返回同一 receipt 与 owner Slice，不创建第二 placement、不重复推进 version 或 outbox；同键冲突输入返回 canonical idempotency failure。
- THEN BOLA、Post 或 CircleGroup identity 非法、跨 Circle group、owner 依赖、内部 version/CAS 或 storage 失败返回 canonical typed failure，owner state、receipt 与 outbox 不产生部分成功；feed/discovery 投影不得被用来伪造成功或 owner readback。

<a id="gwt-008"></a>
### GWT-008 移除 CirclePostPlacement

- GIVEN 调用 Persona 是 Post owner 或目标 Circle moderator，且 owner reader 返回目标 placement 当前为 `active`。
- WHEN Persona 使用稳定幂等键提交 canonical `RemovePostFromCircle`，随后通过 owner named reader 读取同一 placement。
- THEN command receipt 与 fresh nonempty typed `CirclePostPlacementSlice` authoritative readback 收敛到同一 placement identity、推进后的 version 与 `removed` 状态，移除只提交一次 owner state、receipt 与 outbox。
- THEN 相同幂等键重放同一语义命令返回同一 receipt 与 owner Slice，不重复移除、不重复推进 version 或 outbox；同键冲突输入返回 canonical idempotency failure。
- THEN BOLA、placement 不存在、identity 不匹配、并发 version/CAS 或 storage 失败返回 canonical typed failure，原 owner state、receipt 与 outbox 不产生部分变化；feed/discovery 中暂未收敛或已经移除的投影均不替代 owner reader。

<a id="gwt-009"></a>
### GWT-009 置顶 CirclePostPlacement

- GIVEN 调用 Persona 是目标 Circle moderator，且 owner reader 返回目标 placement 当前为 `active` 与明确 pinned 状态。
- WHEN Persona 使用稳定幂等键提交 canonical `PinCirclePost` 启用或取消置顶，随后通过 owner named reader 读取同一 placement。
- THEN command receipt 与 fresh nonempty typed `CirclePostPlacementSlice` authoritative readback 收敛到同一 placement identity、推进后的 version 与请求的 pinned 状态，且只提交一次 owner state、receipt 与 outbox。
- THEN 相同幂等键重放同一语义命令返回同一 receipt 与 owner Slice，不重复推进 version 或 outbox；同键不同 enabled 语义返回 canonical idempotency failure。
- THEN BOLA、非 active placement、identity 不匹配、并发 version/CAS 或 storage 失败返回 canonical typed failure，owner state、receipt 与 outbox 不产生部分变化；Circle feed 的 pinned 展示字段只作为投影收敛结果，不充当 owner readback。

<a id="gwt-010"></a>
### GWT-010 精选 CirclePostPlacement

- GIVEN 调用 Persona 是目标 Circle moderator，且 owner reader 返回目标 placement 当前为 `active` 与明确 featured 状态。
- WHEN Persona 使用稳定幂等键提交 canonical `FeatureCirclePost` 启用或取消精选，随后通过 owner named reader 读取同一 placement。
- THEN command receipt 与 fresh nonempty typed `CirclePostPlacementSlice` authoritative readback 收敛到同一 placement identity、推进后的 version 与请求的 featured 状态，且只提交一次 owner state、receipt 与 outbox。
- THEN 相同幂等键重放同一语义命令返回同一 receipt 与 owner Slice，不重复推进 version 或 outbox；同键不同 enabled 语义返回 canonical idempotency failure。
- THEN BOLA、非 active placement、identity 不匹配、并发 version/CAS 或 storage 失败返回 canonical typed failure，owner state、receipt 与 outbox 不产生部分变化；Circle feed 或 Recommendation 的 featured 展示/排序结果只作为下游投影，不充当 owner readback。

## 6. 依赖

- 前置要求：[`circle-experience-redesign`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 圈子主页与群组详情模板

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：圈子主页与群组详情模板的单请求投影与稳定 case ID。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-002"></a>
### OPEN-002 圈子频道单请求、游标与强类型内容投影

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：单请求、强类型投影、游标增量和缓存收敛合同均有稳定 case ID。
- 完成判定：`GWT-002` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-003"></a>
### OPEN-003 分页读取 CircleGroup 的 owner 合同证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺 `ListCircleGroups` 独立证明 nonempty typed page、稳定筛选分页与 BOLA/canonical failure 的完整直接证据。
- 完成判定：`GWT-003.t1`、`GWT-003.t2` 与 `GWT-003.t3` 各自被真实测试 `spec_ref` 绑定。

<a id="open-004"></a>
### OPEN-004 搜索 CircleGroup 的 owner 合同证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺 `SearchCircleGroups` 独立证明 nonempty typed page、稳定查询分页与可见性/canonical failure 的完整直接证据。
- 完成判定：`GWT-004.t1`、`GWT-004.t2` 与 `GWT-004.t3` 各自被真实测试 `spec_ref` 绑定。

<a id="open-005"></a>
### OPEN-005 读取单个 CircleGroup 的 owner 合同证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺 `GetCircleGroup` 独立证明 authoritative typed slice、BOLA 边界与 canonical failure 的完整直接证据。
- 完成判定：`GWT-005.t1`、`GWT-005.t2` 与 `GWT-005.t3` 各自被真实测试 `spec_ref` 绑定。

<a id="open-006"></a>
### OPEN-006 更新 CircleGroup 的 owner 合同证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺 `UpdateCircleGroup` 独立证明 owner readback 收敛、幂等重放与失败原子性的完整直接证据。
- 完成判定：`GWT-006.t1`、`GWT-006.t2` 与 `GWT-006.t3` 各自被真实测试 `spec_ref` 绑定。

<a id="open-007"></a>
### OPEN-007 创建 CirclePostPlacement 的 owner 合同证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺 `PlacePostInCircle` 的 production Remote/generated-client 证据，以及 command receipt、fresh owner `CirclePostPlacementSlice` readback、幂等冲突和失败原子性的完整直接证明。
- 完成判定：`GWT-007.t1`、`GWT-007.t2` 与 `GWT-007.t3` 各自被真实测试 `spec_ref` 绑定。

<a id="open-008"></a>
### OPEN-008 移除 CirclePostPlacement 的 owner 合同证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺 `RemovePostFromCircle` 的 production Remote/generated-client 证据，以及 removed owner readback、重放、并发冲突和下游投影边界的完整直接证明。
- 完成判定：`GWT-008.t1`、`GWT-008.t2` 与 `GWT-008.t3` 各自被真实测试 `spec_ref` 绑定。

<a id="open-009"></a>
### OPEN-009 置顶 CirclePostPlacement 的 owner 合同证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺 `PinCirclePost` 的 production Remote/generated-client 证据，以及 pinned owner readback、重放、BOLA/version 失败原子性和 feed 投影边界的完整直接证明。
- 完成判定：`GWT-009.t1`、`GWT-009.t2` 与 `GWT-009.t3` 各自被真实测试 `spec_ref` 绑定。

<a id="open-010"></a>
### OPEN-010 精选 CirclePostPlacement 的 owner 合同证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺 `FeatureCirclePost` 的 production Remote/generated-client 证据，以及 featured owner readback、重放、BOLA/version 失败原子性和 feed/Recommendation 投影边界的完整直接证明。
- 完成判定：`GWT-010.t1`、`GWT-010.t2` 与 `GWT-010.t3` 各自被真实测试 `spec_ref` 绑定。
