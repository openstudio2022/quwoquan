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
