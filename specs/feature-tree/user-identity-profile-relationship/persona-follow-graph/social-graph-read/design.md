# social-graph-read 设计方案

## 设计动因

`social-graph-read` 决定外部世界“能看到什么图谱”。如果 read side 不单独设计，主页按钮矩阵、粉丝列表、聊天门禁和 graph 隐私规则就会重新混回写侧逻辑。

本场景设计要冻结四件事：

1. follower / following 分页的稳定游标与过滤策略。
2. `GetRelationship` 与 `RelationshipCapabilityView` 的读投影边界。
3. block、strict isolation、retired persona 对公开图谱读取的影响。
4. legacy owner-level graph 与旧 `RelationTier` 的兼容退出路径。

## 上游输入评审

| 输入 | 当前结论 |
|------|----------|
| `social-graph-read/spec.md` | read side、分页、`RelationshipCapabilityView`、过滤边界清晰 |
| `social-graph-read/acceptance.yaml` | `A1/A2/A3/S1` 可直接映射到 `P1~P4` |
| Journey `persona-follow-graph/design.md` | 已冻结 graph 写读分离与 `ProfileSubject` 主键 |
| `follow-relationship/design.md` | command side 负责写边、事件和 legacy edge 回填，不在本场景重复定义 |
| `owner-subaccount-homepage-unification/design.md` | 主页按钮矩阵应消费 `RelationshipCapabilityView`，不手写布尔组合 |

结论：

- `/design` 准入满足。
- 本场景必须与 `follow-relationship` 使用同一套 key 和兼容迁移口径。

## 对标输入分析

### 外部对标

| 对标对象 | 吸收点 | 不吸收点 |
|----------|--------|----------|
| 微博 | 公开粉丝/关注列表与互关态展示 | 不照搬 owner 暴露与弱隐私策略 |
| 小红书 | 主页关系能力矩阵与 follow list 展示一致性 | 不照搬其页面 IA |
| 微信 | block/关系门禁在消息和资料页必须一致 | 不照搬强关系通讯录读模型 |

### 内部对标

| 文档 / 能力 | 可复用点 |
|-------------|----------|
| Journey 设计 | `ProfileSubject` 作为公开身份主键与展示模型 |
| `follow-relationship` 设计 | command side 只负责写入，不再承担读投影 |
| `content-display-journey-consistency` | canonical key、共享 provider 与 route result 不是图谱真相源 |

## 方案对比

### 方案 A：直接读取 `FollowEdge`，在 UI 侧拼列表项和能力矩阵

核心思路：

- Repository 返回原始 follow 关系或简单布尔。
- 主页、聊天、粉丝页各自推导展示与能力位。

优点：

- 服务端改动最少。
- UI 可按需组装。

缺点：

- 再次把 graph 规则拆散到多个页面。
- block/visibility 过滤容易不一致。
- 无法稳定治理分页串页与 owner 泄露。

### 方案 B：新增重量级物化 graph read table

核心思路：

- 预先生成完整列表项和能力矩阵 projection。
- 所有读取都走物化表。

优点：

- 读性能理论最好。
- UI 接口简单。

缺点：

- 当前阶段成本过高。
- projection 一旦漂移，回填和修复复杂。
- 对 `ProfileSubject` 与 visibility 的联动变更过重。

### 方案 C：查询时组合 `FollowEdge + BlockEdge + ProfileSubject`，能力矩阵作为轻量读投影

核心思路：

- follower / following 读取以 `FollowEdge` 为游标主源。
- 查询时 join `BlockEdge` 与 `ProfileSubject`。
- `RelationshipCapabilityView` 作为轻量读投影返回。

优点：

- 与 PRD 和 Journey 设计最一致。
- 有利于逐步迁移 legacy graph。
- 适合先做 persona-aware graph 的第一版。

缺点：

- 需要设计好过滤后的补页策略。
- `RelationshipCapabilityView` 需要与旧 UI 兼容过渡。

## 选型决策

**选定方案：方案 C**

理由：

1. 它保证图谱读取和按钮矩阵都围绕同一个 read projection，而不是 UI 私有逻辑。
2. 它不引入过重的物化表，同时足以支撑 `A1/A2/A3`。
3. 它最适合承接 legacy graph 双读和 `RelationTier` 兼容退出。

## 关键设计决策

### KD1：分页主游标固定在 `FollowEdge`

`ListFollowers / ListFollowing` 的主游标固定为：

- `createdAt`
- `edgeId` 或等价稳定二级排序键

这样可以保证：

- 重复请求稳定
- 过滤后仍能继续补页
- 不依赖 `ProfileSubject` 的展示字段排序

### KD2：过滤后采用 overfetch + fill 策略

图谱读取不能简单“取一页再过滤”，否则会产生漏页或页大小波动。第一版采用：

1. 按 `FollowEdge` 主游标抓取候选集
2. join `BlockEdge` 与 `ProfileSubject`
3. 过滤 strict/block/retired 不可见项
4. 若当前页不足目标数量，继续按游标 overfetch 直到填满或耗尽

这样可以避免：

- block 过滤导致页内元素过少
- strict isolation 导致翻页重复或漏页

### KD3：基础关系态与能力矩阵分层

冻结两类读投影：

- `RelationshipView`
  - 回答 `not_following / following / followed_by / mutual / self`
- `RelationshipCapabilityView`
  - 回答 `canFollow / canUnfollow / canMessage / canFollowBack / canStartVoiceCall / canStartVideoCall / isBlocked / isBlockedBy`

原则：

- 基础关系态与能力矩阵都属于 read side
- UI 不再手写 `RelationTier + bool` 组合推导能力位

### KD4：visibility、block、retired persona 的公开语义统一

读取时统一遵守：

- `strict`：公开不可见
- block：列表与能力读取都使用最小暴露语义
- retired persona：是否继续出现在公开图谱中，服从 `ProfileSubject` 可见性合同

统一禁止：

- 列表显示了，能力矩阵却仍然可操作
- 能力矩阵泄露超出产品允许范围的 block 事实
- 通过共同粉丝或 mutual 状态间接推断 owner

### KD5：消费者边界只认 read projection

消费方规则：

- 主页按钮矩阵：只认 `RelationshipCapabilityView`
- 聊天 / RTC 门禁：只认能力位
- follower / following 页：只认列表 read model

不允许：

- UI 直接读取 `FollowEdge` 原始对象
- 页面自己根据 follow + block 布尔拼能力矩阵

### KD6：legacy graph 与旧 `RelationTier` 兼容退出

兼容期规则：

- legacy owner-level graph 允许读路径双读映射到主分身
- 旧 `RelationTier` 仅作 UI 兼容层，不再是能力位真相源
- 新页面和新 provider 统一转向 `RelationshipCapabilityView`

退出条件：

- 图谱列表只读 persona-aware edge
- 主页/聊天/RTC 全部停止消费 `RelationTier`

## metadata / codegen 方案

主目录：

- `contracts/metadata/user/follow_edge/`
- `contracts/metadata/user/block_edge/`
- `contracts/metadata/user/user_profile/`

建议补齐：

- `FollowerListItemView`
- `FollowingListItemView`
- `RelationshipView`
- `RelationshipCapabilityView`
- graph list cursor / paging request entity

执行：

- `make -C quwoquan_service verify-metadata`
- `make codegen`
- `make codegen-app`

要求：

- App provider、主页按钮矩阵、聊天门禁全部消费生成 DTO
- 不允许在页面里手写 capability fallback map

## 字段演进、迁移/回填与兼容

### 字段演进

- graph list item 的 identity key 统一为 `profileSubjectId`
- capability view 替代 `RelationTier + bool` 组合
- 旧 `username` 仅保留展示/路由作用

### 迁移 / 回填

- 读路径短期双读 persona-aware edge 与 legacy owner edge
- legacy owner edge 统一映射到主分身 `profileSubjectId`
- `RelationTier` 通过 adapter 从 `RelationshipCapabilityView` 派生，供旧组件过渡

### 退出条件

- 新旧列表、按钮矩阵、聊天门禁全部切到 capability view
- legacy owner edge 与 `RelationTier` 适配层不再被命中

## feature flag、观测、SLO 验证与回滚方案

建议开关：

- `ops.user.persona_graph_v1`

关键观测：

- `graph_list_latency_ms`
- `graph_page_drift_count`
- `graph_filter_mismatch_count`
- `relationship_capability_mismatch_count`
- `graph_legacy_edge_read_count`

回滚原则：

- 关闭 persona-aware graph 读开关后，可退回旧只读路径
- 新增 `RelationshipCapabilityView` 生成物可保留，不强制删除
- 回滚不得破坏已完成的 follow edge 回填

## TDD / ATDD 策略

- `T1_schema`
  - list item、cursor、relationship view、capability view、filter 规则
- `T2_module_interaction`
  - 主页按钮矩阵、粉丝列表、聊天门禁消费 projection
- `T3_cross_service_integration`
  - `FollowEdge + BlockEdge + ProfileSubject` 联调、过滤补页、legacy graph 双读
- `T4_user_journey`
  - 查看粉丝/关注、切主页按钮、被 block / strict isolation / retired persona 图谱读取
- `T4_release_rehearsal`
  - graph read rollback、page drift 与 capability mismatch telemetry

## plan slice 与 T1~T4 证据矩阵映射

| Slice | 目标 | 对应验收 | 主要证据 |
|-------|------|----------|----------|
| `P1` | 冻结 graph list、cursor、capability projection metadata | `A1/A2` | `T1_schema` |
| `P2` | 建立 codegen 与 graph provider/consumer 基线 | `A1/A2` | `T1_schema`, `T2_module_interaction` |
| `P3` | 落地 overfetch+fill、filter、capability 消费与 legacy 双读 | `A2/A3` | `T3_cross_service_integration`, `T4_user_journey` |
| `P4` | 验证灰度、回滚、page drift 与 capability telemetry | `A3/S1` | `T3_cross_service_integration`, `T4_release_rehearsal` |

## 未来演进

- 如果未来 graph 查询规模显著上升，再评估是否引入更重的 projection / cache 层，但前提仍是保留 `ProfileSubject` 与 capability view 作为统一 contract。
- 当所有消费者都切到 capability view 后，再统一清理旧 `RelationTier` 和局部布尔推导逻辑。
