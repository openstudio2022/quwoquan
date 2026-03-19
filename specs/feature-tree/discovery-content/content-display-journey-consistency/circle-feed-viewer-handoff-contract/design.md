# circle-feed-viewer-handoff-contract 设计方案

## 设计动因

圈子来源进入 viewer 目前仍处于“能打开，但协议不完整”的状态：

1. `section_creations.dart` 只传了部分 interaction snapshot，未完整传入 `followingUsers`、`likedPosts`、`savedPosts` 与正文语义。
2. viewer 返回后，圈子来源只吸收部分计数，没有完整吸收最终状态。
3. circle 与 discovery 入口各自演化，已经出现两套 handoff / dismiss 吸收语义。

本 Scenario 的目标是冻结 `circle feed -> viewer -> profile -> circle feed` 的 handoff / return contract，并与 discovery 入口保持同构。

## 上游输入评审

| 输入 | 结论 |
|------|------|
| `circle-feed-viewer-handoff-contract/spec.md` | 范围与验收清晰，circle 已正式纳入本次 Journey |
| `content-display-journey-consistency/design.md` | 已冻结 shared provider 为主、route result 为补强的总体方案 |
| `MediaViewerExtra` / `MediaViewerResult` 现状 | 已有基础结构，但字段语义偏 discovery-only，需要补齐 circle 来源上下文 |
| `section_creations.dart` 现状 | 是当前圈子来源进入 viewer 的主入口，且正是本次问题集中点 |

## 对标输入分析

| 对标 | 吸收点 | 不吸收点 |
|------|--------|----------|
| 小红书圈层内容流 | 不同来源进入详情后交互语义一致 | 不照搬其圈层产品定义 |
| 微博超话内容流 | 来源上下文保留，但详情协议不分叉 | 不照搬其 feed 结构 |

内部对标：

- discovery 的 `MediaViewerExtra` / `MediaViewerResult` 已经证明“完整 extra + result 补强”是可落地路径，circle 应与其同构而不是另起一套。

## 方案对比

### 方案 A：circle 保持独立 handoff 协议

优点：

- 对圈子入口改动最小。

缺点：

- 与 discovery 继续分叉。
- 难以共享 viewer/profile 同步链路。

### 方案 B：circle 只传最小 ID，viewer 自拉完整数据

优点：

- handoff 结构最简。

缺点：

- 首屏会出现缺正文、缺状态或额外请求。
- 圈子来源回到原来源时仍缺明确 absorb contract。

### 方案 C：circle 与 discovery 统一 extra/result 协议

优点：

- 首屏完整。
- 来源差异只保留在 source context。
- 便于共享同一 viewer/profile/provider 主链路。

缺点：

- 需要改造现有圈子入口与返回吸收逻辑。

## 选型决策

选定方案：**方案 C**

原因：

1. 这与 Journey 的 J1 要求完全一致。
2. circle 只做来源上下文承载，最符合对象边界。
3. 对后续 photo/video/moment 三类媒体统一最友好。

## 关键设计决策

### KD1：circle 只保留来源上下文

circle 来源上下文包括：

- `CircleId`
- `source = circle`
- `rawPostsById`
- 列表顺序与当前索引

circle 不保留独立的 follow / like / save 真相源。

### KD2：统一 extra 结构

`MediaViewerExtra` 对 circle 与 discovery 保持同构，circle 只比 discovery 多出来源上下文字段：

- `posts`
- `dtoPosts`
- `initialIndex`
- `category`
- `source`
- `circleId`
- `rawPostsById`
- `interactionSnapshot`

禁止 circle 另建 `CircleMediaViewerExtra`。

### KD3：统一 dismiss absorb 结构

`MediaViewerResult` 作为来源页补强吸收协议保持统一：

- `followingUsers`
- `likedPosts`
- `savedPosts`
- `postLikesCount`
- `postBookmarksCount`
- `postSharesCount`

circle 返回后必须完整吸收，而不是只处理 like/share 数字。

### KD4：正文与 projection 一致性

圈子来源进入 viewer 时：

- photo / video / moment 的正文都必须通过 projection 带入
- viewer 首屏不得依赖额外自拉去补正文
- `PostSummaryView.fromDto()` 必须与 DTO 的 canonical body 保持一致

### KD5：provider 与 route result 的职责边界

- shared provider：负责长生命周期最终状态
- route result：负责来源页即时补强与 UI 收敛
- 当 provider 与 result 都到达时，以 provider 最终状态为准，result 只负责补强来源局部展示

## metadata / codegen 方案

本 Scenario 不新增 circle 专属 metadata 真相源。

依赖的 metadata / codegen 变化来自：

- `content/post` canonical author key 与正文投影
- `user/follow_edge` 的 `RelationshipCapabilityView`
- `GetAppConfig` 对 sync 参数的输出

App 侧主要是 contract 结构演进，不新增 codegen 目标文件名或圈子专属 DTO。

## 字段演进、迁移 / 回填、双读双写

### 字段演进

- circle 来源使用统一 `MediaViewerExtra` / `MediaViewerResult`
- interaction snapshot 从局部计数扩展为完整状态集合 + 计数

### 迁移 / 回填

- 先补齐 circle 入口传参，再补齐返回吸收逻辑
- 兼容期允许 circle 旧入口存在，但 behind feature flag

### 双读 / 双写

- 本 Scenario 不引入长期双写
- 兼容期允许旧 absorb 逻辑与新 absorb 逻辑并存，但只启用一套 feature flag 路径

## feature flag、观测、SLO 验证与回滚

### feature flag

- `ops.content.circle_viewer_handoff_v1`

### 观测

- `circle_viewer_handoff_missing_field_total`
- `circle_viewer_result_partial_absorb_total`
- `circle_viewer_reentry_mismatch_total`

### SLO

- circle 来源进入 viewer 首屏不额外补拉正文
- 返回 circle 后 UI 收敛 `p95 < 100ms`

### 回滚

1. 关闭 `circle_viewer_handoff_v1`
2. 回退到圈子旧入口
3. 保持 viewer 与 discovery 旅程不受影响

## TDD / ATDD 策略

| 验收 | 测试层 | 策略 |
|------|--------|------|
| A1 | T1, T2, T3 | extra contract、widget handoff、integration 首屏完整性 |
| A2 | T2, T3, T4 | result absorb、返回重入、profile 往返闭环 |
| A3 | T1, T2, T3 | provider/source-of-truth 边界、弱网 pending intent |
| S1 | T4 | circle 灰度与回滚专项回归 |

## plan slice 与 T1~T4 证据矩阵映射

| Slice | 目标 | 主要验收 | 主要证据 |
|-------|------|----------|----------|
| P1 | 冻结 circle extra/result 契约 | A1 | T1, T2 |
| P2 | 接入统一 viewer 与来源吸收逻辑 | A1, A2 | T2, T3 |
| P3 | 对齐 provider 真相源与弱网行为 | A3 | T2, T3 |
| P4 | 完成灰度、回滚与旅程回归 | S1 | T4 |

## 未来演进

- 将更多非 discovery 来源接入统一 handoff adapter。
- 在统一 adapter 稳定后，收缩圈子页中与 viewer 强耦合的局部状态代码。
- 若后续新增来源页，默认要求复用此同构协议，而不是再新建 extra/result 类型。
