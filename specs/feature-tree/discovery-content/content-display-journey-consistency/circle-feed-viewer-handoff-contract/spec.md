# L3 特性：circle-feed-viewer-handoff-contract

## 背景与动机

当前圈子流中的 post 虽已有部分进入媒体浏览器的路径，但 handoff 仍不完整：

- 某些来源只带了计数，没有带完整关系态与互动状态；
- viewer 返回后只回写了部分数字，没有完整吸收最终状态；
- 文案、作者信息、来源上下文与 discovery 旅程未形成统一协议。

本 scenario 的目标是把 `circle feed -> viewer -> profile -> circle feed` 的 handoff 冻结为正式契约。

## 目标用户

- 在圈子中浏览图片、视频、微趣媒体并进入沉浸式浏览器的用户。
- 从圈子流进入作者主页并返回后，希望圈子流与 viewer 状态一致的用户。
- 在圈子来源与 discovery 来源间切换时，希望状态表现完全一致的用户。

## 功能范围

### F1：圈子来源进入 viewer 的统一 handoff

- 圈子 post 进入 viewer 时必须传入：
  - `PostId`
  - `authorProfileSubjectId`
  - post 标题/正文/媒体资源
  - 当前互动状态 snapshot
  - 当前来源上下文（`CircleId`、source）

### F2：圈子来源退出 viewer 的统一回写

- viewer 返回时必须回写：
  - likedPosts / savedPosts / followingUsers
  - post like/share/bookmark 等最终计数
- 圈子来源不得只回写部分数字。

### F3：与 discovery 旅程协议一致

- discovery 与 circle 的 viewer handoff 字段集合必须保持同构。
- circle 作为来源上下文承载层，不新增第二套作者关系态或 post 互动态真相。

## Out of Scope

- 圈子 feed 排序、推荐、召回。
- 圈子详情壳层视觉重做。
- 非媒体类 post 的 viewer 能力扩展。

## 约束

- circle 只承载来源上下文，不拥有 `follow` 与 `post interaction` 真相源。
- 所有 handoff 字段必须兼容 content post projections 与 `PostSummaryView` 消费模型。
- 不允许为 circle 额外维护一套 viewer route、DTO 或状态规则表。

## 对标输入与吸收结论

| 对标 | 借鉴点 | 不借鉴点 |
|------|--------|----------|
| 小红书圈子/群组内容流 | 来源流进入详情后状态不应分叉 | 不照搬其圈子产品形态 |
| 微博超话/圈层内容流 | 不同来源进入详情页后互动语义一致 | 不照搬其 feed 模型 |

吸收结论：

- circle 只是来源，不应成为另一套状态源。
- discovery 与 circle 的差异应只体现在来源上下文，而不是 viewer 协议本身。

## 角色分工

- 产品：冻结圈子是否纳入范围、返回回写闭环是否为强规格。
- 架构：冻结 circle source context、handoff payload、回写协议。
- 客户端：落地圈子入口、viewer extra/result、返回吸收逻辑。
- 云端：确保 circle feed payload 与 content projections 一致或可映射。
- 测试：覆盖 circle -> viewer -> profile -> return 的完整闭环。

## 既有 Story 覆盖矩阵

| 既有节点 | 当前职责 | 本 scenario 处理方式 |
|----------|----------|----------------------|
| `moment/photo/video-display-journey` | 各媒体类型旅程 | 继续负责内容类型本身，本 scenario 负责 circle 来源 handoff |
| `viewer-profile-state-sync-contract` | viewer 与 profile 的同步协议 | 直接依赖 |
| `works-immersive-viewer` | 作品 viewer 表现层 | 消费 handoff 结果，不新增 circle 专属壳层 |

## 数据生命周期合同

- circle feed entry
  - 创建来源上下文：`CircleId + source + rawPostsById`
  - 构建 viewer extra：包含 post 数据与互动 snapshot
- viewer dismiss
  - 返回 `MediaViewerResult`
  - circle feed 吸收最终状态
- profile return
  - 通过统一 provider 自动同步回 circle feed，无需 circle 单独重新推断关系态

## 小趣 / 权限 / 分享边界

- 本 scenario 不涉及助手链路。
- circle feed 仅继承 `RelationshipCapabilityView` 权限结果，不自行决定 follow/message/call 可用性。
- 分享仅要求状态与计数回写一致，不扩展分享流程。

## 非功能目标

- 圈子来源进入 viewer 的 handoff 不得导致首屏额外自拉数据。
- circle -> viewer -> return 闭环下，状态回写 `p95 < 100ms` 完成界面收敛。
- 弱网下 circle 来源不得丢失 pending interaction intents。

## 迁移、灰度与回滚要求

- 先冻结 circle handoff contract，再改现有圈子入口实现。
- 灰度由主 journey 的统一 feature flag 与 `sys.client_state_sync.*` 控制。
- 回滚时可退回 circle 旧入口，但不得破坏 discovery 旅程。

## 验收重点

1. 圈子流正式纳入本次 PRD 范围，并有独立 scenario 承载。
2. circle 进入 viewer 的字段集合与 discovery 保持同构。
3. viewer 返回后，circle 不再只回写数字，而是完整吸收最终状态。
4. 进入 `/design` 后不再需要重新讨论“圈子是否属于来源范围”。
