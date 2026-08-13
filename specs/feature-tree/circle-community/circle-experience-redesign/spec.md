# L2 Business Capability：群组发现与详情体验 (`circle-experience-redesign`)

> 所属领域：[`circle-community`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

按群组类型提供一致的发现、详情与协作入口

## 2. 范围与非目标

### In Scope

- 由本目录 Story 组合交付群组发现、筛选、详情与协作入口的一致体验。

### Out of Scope

- 其他 L2 的事实所有权、metadata schema 与实现施工步骤。

## 3. Journey / Scenario 贡献

- [`JNY-008 / SCN-014`](../../spec.md#scn-014)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：按群组类型提供一致的发现、详情与协作入口，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。

## 4. Story



- [`circle-homepage-redesign`](./circle-homepage-redesign/spec.md)：单请求、强类型投影、游标增量和缓存收敛合同均有稳定 case ID。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 circle experience redesign 能力 SIT

- 本能力必须组合直属 Story 与公开契约，交付“按群组类型提供一致的发现、详情与协作入口”所定义的业务结果；失败终态必须可区分且不得伪造成功。

<a id="req-002"></a>
### REQ-002 圈子主页频道聚合与分页体验

- 推荐频道首次进入只读取 recommended 聚合切片；用户显式切换我的频道后才读取 mine 切片，匿名状态保持安全空态和登录续接。
- 分类、二级分类、scope、sort 与 cursor 均由服务端解释；端侧只消费强类型 Slice、保存 nextCursor 并追加加载，不能重排、重新过滤或合成跨圈内容。
- 分页没有重复或遗漏；切换频道、缓存命中、Membership/Placement/Post 失效后的内容与圈子卡片一致。
- 10k/100k 数据集的 Mongo explain 使用声明索引，P95 小于等于 800ms；请求、缓存命中/失效与失败有同源 telemetry。

<a id="req-003"></a>
### REQ-003 新用户：需要在统一入口里快速找到兴趣圈或组织主页

- 新用户：需要在统一入口里快速找到兴趣圈或组织主页。
- 建立统一 domain taxonomy 配置文件，定义领域 ID 及其属性。
- 群组卡片统一使用类型徽章区分 `圈子 / 学校 / 院系 / 班级 / 公司 / 部门` 等详情模板。
- 圈子频道默认只读取 `recommended` 聚合切片；已认证用户主动切换后才读取 `mine`，匿名状态不得请求或推导成员范围。
- `ListCircleDiscoveryFeed` 是分类、成员范围、展示位与内容的唯一聚合读接口；客户端不得以 `listCircles` 后逐圈读取内容重建频道。
- 频道使用服务端 keyset cursor、稳定排序和强类型 `CircleDiscoveryFeedPageSlice`；端侧只保存 cursor 并追加既有顺序，不能重排或以本地过滤改变服务端 scope。
- 不在客户端补造 Circle、Membership、Post 或 Placement 的内容、关系或展示字段；Remote 空态与失败必须保持结构化空态/恢复面。
- 领域标签配置必须为 metadata YAML，经 codegen 生成端云代码。
- 首页和搜索的统一用户词必须是 `群组`。
- 推荐排序必须支持降级到按热度排序。
- 圈子的用户关系轨只有「加入」（CircleMembership）一条；不提供「关注圈子」第二关系轨入口。
  读模型中的 `FollowSubjectKind.circle` 仅服务首页关注频道的历史投影展示，禁止在圈子页面
  新增关注圈子写入口或以本地假状态模拟关注（防双轨漂移；本条为裁决，非 OPEN）。

## 6. 契约与依赖

- 上游能力：[`circle-community`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 circle experience redesign 能力 SIT

- GIVEN 执行“circle experience redesign 能力”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“circle experience redesign 能力”对应动作。
- THEN 直属 Story 共同交付“按群组类型提供一致的发现、详情与协作入口”，失败终态可区分且不产生伪成功事实。

<a id="sit-002"></a>
### SIT-002 圈子主页频道聚合与分页体验

- GIVEN 执行“圈子主页频道聚合与分页体验”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“圈子主页频道聚合与分页体验”对应动作。
- THEN 推荐频道首次进入只读取 recommended 聚合切片；用户显式切换我的频道后才读取 mine 切片，匿名状态保持安全空态和登录续接。
- THEN 分类、二级分类、scope、sort 与 cursor 均由服务端解释；端侧只消费强类型 Slice、保存 nextCursor 并追加加载，不能重排、重新过滤或合成跨圈内容。
- THEN 分页没有重复或遗漏；切换频道、缓存命中、Membership/Placement/Post 失效后的内容与圈子卡片一致。
- THEN 10k/100k 数据集的 Mongo explain 使用声明索引，P95 小于等于 800ms；请求、缓存命中/失效与失败有同源 telemetry。

## 8. 开放事项

（当前无开放事项：SIT-001/SIT-002 均已由真实测试绑定。）
