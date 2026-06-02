# L2 特性：feed-orchestration-recommendation

## 功能说明
- 细化 feed-orchestration-recommendation 特性的功能边界与端云协同行为。
- **端侧反馈 + 实时推荐链路**：发现流/详情由端上报行为（曝光、点击、停留、点赞等）→ 云侧 HotPath/FeedbackRecorder 落库 → 下次 GetFeed 时推荐引擎按 session 做实时排序与去重。本节点覆盖「端云行为上报契约 + feed 请求带 session + 发现流曝光/互动上报」的打通与验收。

## 约束
- 契约与字段策略必须与 OpenAPI 与 metadata 保持一致。

## 验收标准
- A1：功能路径可执行且输出稳定。
- A7：契约一致性校验通过。
- A8：对应自动化测试映射完整。

## 首页交集与多形态信息流改版（V8）

### 目标

首页从“所有频道复用同一个微博式 feed 组件”升级为“频道意图驱动的多形态信息流”：

- `关注` 保持单列关系流，强调作者、时间、正文、互动与关系信任。
- `精品` 保持侵入式消费体验，承载高完成度作品、视频和长文阅读入口。
- `推荐 / 校园 / 旅行 / 摄影` 在手机端采用双列发现流，提高浏览密度和主动选择效率。
- `科技 / 汽车` 与校园、旅行、摄影一致，手机端统一双列发现流；文章、长评、口碑等强解释内容通过详情页与对象页承接，而不是在首页单独切一套 full-span 主布局。
- `交集` 从顶部孤立横滑 rail 升级为 full-span 解释模块 + 卡片内轻量理由 + 对象/实体主页承接。

### 体验规则

- 手机 `<600px`：推荐、校园、旅行、摄影默认 2 列；关注固定 1 列；精品走侵入式。
- 平板/宽屏：按响应式列数扩展，但交集 spotlight、文章大卡、口碑/问答等模块跨全部列。
- 双列卡只展示封面、标题/短正文、作者小信息和一行交集理由；完整正文、复杂行动与解释放到详情页、对象页或 full-span 模块。
- 同一个 `PostBaseDto` / `ContentSurfaceView` / `IntersectionReason` 支持单列、双列、侵入式、对象页承接四类展示；禁止为双列新建第二套业务列表。

### 交集闭环

- Feed item 的 `intersectionReasons` 是首页交集模块和卡片内理由的唯一来源。
- 对象对直打的 `shared-tags` 继续映射为 `IntersectionReason`，由对象/实体主页 `ObjectIntersectionCard` 承接。
- 用户在交集模块点击关注、加入圈子、加联系人时，必须回流 `intersectionDimension` 和 `intersectionTagRefs`，支撑 `intersection_conversion_rate` 下钻。
- 小趣入口消费 `intersectionRefs / objectType / actionTargetId`，用于解释“为什么推荐给你”，端侧不本地拼装交集文案。

## 关注页对象列表与未读变化（V9）

### 目标

关注频道是登录态主页，不只是“关注内容 feed”。进入关注频道后，顶部先展示用户关注的人、圈子和地点/事物主页列表，类似早期 stories 的横向浏览效率，但前台不使用 stories 这个概念。

### 访问规则

- 未登录时，关注频道整体不可查看，包括顶部关注对象列表和下方关注 feed。
- 点击“关注”tab、左右滑进入关注、深链 `/following` 都必须走 `AuthGateReason.followingFeed`。
- 登录后才能加载关注对象列表和关注 feed。

### 顶部关注对象列表

- 前台模块名：`关注动态`。
- 端侧组件名：`FollowingSubjectStrip`。
- 单项模型：`FollowingSubjectItem`。
- 支持对象类型：`user`、`circle`、`homepage`。
- 展示形态：横向头像/封面列表，名称 1 行；用户用头像，圈子/地点和事物主页用封面或 fallback 图标。
- 点击对象后进入对应主页：用户主页、圈子详情、地点和事物主页。

### 上次访问后变化红点

- 小红点只表示“该对象自你上次进入后有变化”，不是消息未读。
- 云侧返回 `lastVisitedAt`、`latestChangedAt`、`unreadChangeCount`、`hasUnreadChanges`。
- 端侧看到 `hasUnreadChanges=true` 时在头像右上角显示红点。
- 用户点击对象并成功进入主页后，端侧调用 `MarkFollowingSubjectVisited`；本地可乐观隐藏红点，下一次刷新以云侧为准。

### 提示语

- 登录标题：`登录后查看关注`
- 短提示：`登录后查看你关注的人、圈子和地点动态`
- 登录页副文案：`登录后会同步你的关注列表，并提示上次访问后的新变化。`
- 空态标题：`还没有关注的人、圈子或地点`
- 空态副文案：`去推荐、校园、旅行里关注感兴趣的对象，回来这里查看它们的新动态。`

### 端云契约

- 新增 `user/following_subject` metadata，归属 user 域，聚合用户关注对象读模型。
- `ListFollowingSubjects` 返回用户、圈子、地点和事物主页三类对象。
- `MarkFollowingSubjectVisited` 写入当前 viewer 对目标对象的 `lastVisitedAt`。
- 变化水位 `latestChangedAt` 由对象域写入或投影，关注域只维护 viewer 维度访问水位。
- 如果某类对象的 follow 能力尚未完全可写，不能在 UI 本地伪造列表；必须由 seed/mock repository 与远端契约同形提供。
