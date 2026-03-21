# follow-relationship 设计方案

## 设计动因

`follow-relationship` 是分身社交图谱的 command side。如果 follow 写入仍然挂在 `UserProfile` 聚合或 UI 布尔状态里，owner/persona/profileSubject 的边界就会立刻被打穿。

本场景设计要一次性回答：

1. 关注边的主对象是谁。
2. follow / unfollow 如何做到 persona-aware、幂等、可审计。
3. `BlockEdge`、计数副作用、legacy owner-level follow 如何协同迁移。

## 上游输入评审

| 输入 | 当前结论 |
|------|----------|
| `follow-relationship/spec.md` | `FollowEdge` command side、block gate、事件副作用边界清晰 |
| `follow-relationship/acceptance.yaml` | `A1/A2/A3/S1` 可直接映射到 `P1~P4` |
| Journey `persona-follow-graph/design.md` | 已冻结 graph 写读分离与 `ProfileSubject` 主键 |
| `social-graph-read/spec.md` | read side 将组合 `FollowEdge + BlockEdge + ProfileSubject`，本场景无需再定义列表读取 |
| 现有图谱与主页消费路径 | 仍有 owner/user 级 follow 兼容需求，需要在设计里明确回填与退出条件 |

结论：

- `/design` 准入满足。
- 本场景必须与 `social-graph-read` 配套设计，但写侧 contract 先于读侧落地。

## 对标输入分析

### 外部对标

| 对标对象 | 吸收点 | 不吸收点 |
|----------|--------|----------|
| 微博 | 公开 follow 图谱需要稳定的 command side 和事件传播 | 不照搬其 owner 暴露模型 |
| 小红书 | 创作者主页 follow 按钮的即时性与幂等语义 | 不照搬客户端局部布尔状态模型 |
| 微信 | block/follow 门禁不能互相绕开 | 不照搬通讯录式强关系逻辑 |

### 内部对标

| 文档 / 能力 | 可复用点 |
|-------------|----------|
| Journey 设计 | `FollowEdge` command side、`ProfileSubject` 主键 |
| `content-display-journey-consistency` | provider/outbox 不应成为关系真相源 |
| `owner-subaccount-homepage-unification` | 主页按钮矩阵最终消费 read projection，而不是 command 结果 |

## 方案对比

### 方案 A：继续把 follow 写入放在 `UserProfile` 聚合

核心思路：

- `UserProfile` 直接保存 follow 关系或负责全部写入逻辑。
- 计数和关系边不做明确拆分。

优点：

- 实现集中。
- 不需要新 command object。

缺点：

- `UserProfile` 会被高频图谱写入拖垮。
- 无法自然支撑 MongoDB 图谱边与事件副作用。
- persona-aware follow 很容易再次退回 owner 语义。

### 方案 B：`FollowEdge` 独立 command side，计数通过事件同步

核心思路：

- follow/unfollow 全部落在 `FollowEdge`。
- 计数和按钮矩阵都不在 command side 内部硬耦合。
- `UserProfile` 只通过事件更新冗余统计。

优点：

- 与 DDD 边界和现有存储分区一致。
- 幂等、block gate、审计语义更好表达。
- 有利于后续高并发图谱扩展。

缺点：

- 需要设计事件、回填和读写配合。
- 计数是最终一致。

### 方案 C：新增独立 graph command service 或 graph DB 专用写入

核心思路：

- 把 follow 完全抽到单独 graph service / graph DB。
- user 域只做 owner/persona 解释。

优点：

- 理论上更适合超大规模图谱。

缺点：

- 当前阶段明显过度设计。
- 会让 Journey 范围的 user 域真相源再次被拆散。
- 迁移与治理成本过高。

## 选型决策

**选定方案：方案 B**

理由：

1. 它保持 `FollowEdge` 作为 user 域独立业务对象，和当前 PRD 完全一致。
2. 它能自然表达 `A1/A2/A3` 的主体、幂等、block gate 与计数副作用。
3. 它比方案 C 更符合当前仓库阶段，不会过度拆服务。

## 关键设计决策

### KD1：persona-aware follow 以 `ProfileSubject` 为主键

follow command 不再接受 owner 级主体，统一使用：

- `actorProfileSubjectId`
- `targetProfileSubjectId`
- `source`
- `requestId` 或等价幂等键

约束：

- owner 不再作为默认 follow 主体
- 显式改用其它分身时，command 仍必须落到 `ProfileSubject` 级 key

### KD2：幂等与唯一约束由 `FollowEdge` 主对象承担

唯一约束冻结为：

- `actorProfileSubjectId + targetProfileSubjectId`

幂等规则：

- 重复 follow 返回已存在成功语义
- unfollow 不存在边时返回安全 no-op 或明确可恢复语义
- 不能通过前端局部状态判断是否重复提交

### KD3：block gate 在 command side 前置判定

`BlockEdge` 是 follow 写入前置门禁：

- 任一方向 block 存在时，follow 被拒绝或无效化
- 失败语义不得泄露超出产品允许范围的 block 细节
- follow command 不允许绕过 `BlockEdge` 直接写边

### KD4：事件驱动计数修正

写侧完成后发布：

- `UserFollowed`
- `UserUnfollowed`

下游消费：

- `UserProfile` 更新 `followerCount / followingCount`
- 通知/推荐系统读取事件自行修正

原则：

- `FollowEdge` 成功写入不依赖计数同步即时完成
- 计数失败可重放修正，但不能影响主边幂等性

### KD5：legacy owner-level follow 迁移到主分身

历史 follow 若仍以 owner/user 级 key 存在，必须在 persona-aware follow 开关打开前完成迁移：

- 为每个 owner 确认主分身 `profileSubjectId`
- 将 legacy follow edge 回填到主分身 key
- 回填期读路径允许双读：
  - 优先 persona-aware edge
  - 兼容 legacy owner edge 映射

退出条件：

- 新 follow 全量只写 persona-aware edge
- 旧 owner-level edge 不再被读路径命中

### KD6：App / repository 边界只消费 command contract

App 侧 follow 按钮、关系操作菜单、推荐入口只允许调用统一 follow repository / facade：

- 不直接改写主页局部布尔状态
- 不在 UI 手写 `isFollowing` 作为真相源
- command result 只负责反馈写入结果；真正的按钮矩阵由 read side 收敛

## metadata / codegen 方案

主目录：

- `contracts/metadata/user/follow_edge/`

建议补齐：

- `FollowCommandRequest`
- `UnfollowCommandRequest`
- `FollowCommandResult`
- `UserFollowed / UserUnfollowed`
- 幂等、block gate 相关错误码和 request context

执行：

- `make -C quwoquan_service verify-metadata`
- `make codegen`
- `make codegen-app`

要求：

- App follow repository 必须消费 path builder、operation 常量、错误码枚举
- 不允许在 UI 或 provider 中硬编码 follow API path 或错误文案

## 字段演进、迁移/回填与兼容

### 字段演进

- command 主键统一切到 `ProfileSubject`
- source 作为审计辅助字段保留
- `userId` / owner-level follow 只作为迁移兼容输入，不再写入新边

### 回填

- legacy owner-level follow edge 映射到主分身
- 为事件补齐 actor/target `profileSubjectId`
- 为计数修正建立幂等 replay 机制

### 兼容策略

- 短期双读、单写
- 长期只保留 persona-aware edge

## feature flag、观测、SLO 验证与回滚方案

建议开关：

- `ops.user.persona_graph_v1`

关键观测：

- `follow_command_latency_ms`
- `follow_duplicate_request_count`
- `follow_block_rejection_count`
- `follow_counter_mismatch_count`
- `follow_legacy_edge_read_count`

回滚原则：

- 关闭开关后可回退到旧写路径
- 已迁移的 persona-aware edge 不删除
- 计数修正继续以事件重放方式收敛

## TDD / ATDD 策略

- `T1_schema`
  - follow command、event、block gate、错误码、迁移约束
- `T2_module_interaction`
  - follow 按钮、推荐入口、command 状态机
- `T3_cross_service_integration`
  - follow/unfollow、block gate、计数事件、legacy edge 回填
- `T4_release_rehearsal`
  - persona-aware follow rollback、计数对账、迁移演练

## plan slice 与 T1~T4 证据矩阵映射

| Slice | 目标 | 对应验收 | 主要证据 |
|-------|------|----------|----------|
| `P1` | 冻结 follow command、event、block gate metadata | `A1/A2` | `T1_schema` |
| `P2` | 建立 codegen 与 persona-aware follow repository 基线 | `A1/A2` | `T1_schema`, `T2_module_interaction` |
| `P3` | 落地幂等、block gate、计数同步与迁移逻辑 | `A2/A3` | `T3_cross_service_integration` |
| `P4` | 验证灰度、回滚、legacy edge 退出与审计指标 | `A3/S1` | `T3_cross_service_integration`, `T4_release_rehearsal` |

## 未来演进

- 当 persona-aware follow 稳定后，再评估是否需要把更重的图谱能力拆到独立服务，但那将是新的 Journey，不在当前范围。
- 后续如接入本地 outbox 或批量 follow 场景，也必须复用同一 command contract，不新增第二套 follow 语义。
