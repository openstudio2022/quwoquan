# Owner/SubAccount 一体化个人主页统一改版

## 背景与动机

当前个人主页存在两类根问题：

1. UI 与交互割裂：`MyProfilePage/ProfileShell` 与 `OtherProfilePage/AuthorProfile` 并行维护，导致滚动、拉伸、按钮矩阵、Tab 结构和视觉风格长期漂移。
2. 端云契约失真：用户域已经明确 `OwnerAccount` 与 `SubAccount` 双层身份模型，但个人主页仍在 `userId / subAccountId / username / Persona` 多套语义之间摇摆，端侧大量直接消费手写 `Map<String, dynamic>`，无法进入稳定的 metadata-first 开发。

这次 Story 的目标不是单纯“重画页面”，而是把 `owner` 与 `subAccount` 一体化主页的交互规格、metadata 消费边界和端云消费链一次性收拢，为后续 `/dev` 提供稳定设计基线。

补充冻结：

- user 域关于 `SubAccountProfileView / SubAccountProfileMutation / 分身可见性 / 记录归因` 的真相源归 `persona-follow-graph/persona-profile-subject-and-visibility`。
- 本场景消费这些 user 域契约来构建主页与资料编辑体验，不再拥有分身生命周期与公开身份模型的主定义权。

## 目标用户

- 默认只有一个 `owner` 账号的普通用户。
- 有身份隔离需求、会创建多个 `subAccount` 的用户。
- 查看自己主页、查看他人主页、编辑资料并同步到其它身份的用户。

## 功能范围

### F1: 主页主体模型统一

- 不再引入单独的“公开主页实体”。
- `owner` 和每个 `subAccount` 都各自拥有一个别人可见的主页。
- `subAccount` 创建时默认继承 `owner` 的资料基线，但允许局部覆写。
- 对外路由仍保持 `/user/{username}`，但端云契约内统一为 `ProfileSubject` 语义，避免继续混用 `userId / subAccountId / username`。

### F2: 资料编辑与同步提示

- 编辑入口进入统一的资料编辑流。
- 当修改 `owner` 或某个 `subAccount` 时，保存后需要提示是否将本次变更同步到其它关联身份。
- “是否同步给 owner / 其它 subAccount” 必须进入写入契约，不能只停留在前端临时状态。

### F3: 我的主页与他人主页统一壳层

- `我的主页` 与 `他人主页` 最终都落到统一的 `ProfileShell`。
- 差异只由 `self / other / relationship state` 驱动，不再保留双轨滚动与拉伸实现。
- 头部布局统一为：头像侵入背景约 `1/3`，名字与资料主体在 profile 区 `2/3`，个人介绍独立成块。

### F4: 关系态按钮矩阵

- `self`：资料可编辑，保留设置入口。
- `未关注`：`关注 + 私信`。
- `我关注 Ta`：`已关注 + 私信`。
- `Ta 关注我`：`回关 + 私信`。
- `互关`：`消息 + 语音通话 + 视频通话`。
- 本次版本不启用 `same_interest / close_friend` 等扩展关系层级作为主页主流程前提。

### F5: 一级/二级 Tab 结构重定

- 一级 Tab 固定为：`创作 | 圈子 | 互动`，默认选中 `创作`。
- 一级 Tab 视觉语义对齐首页 `CenteredScrollableTabBar`：字重、下划线、热区一致，但间距更大。
- `创作` 内保留左对齐二级胶囊筛选：`全部 | 微趣 | 图片 | 视频 | 文字`。
- `互动` 内保留左对齐二级胶囊筛选：`赞 | 评论 | 转发`。
- 我的主页额外支持互动方向切换 `收到 | 发出`；他人主页仅展示 `Ta 收到` 的公开互动。
- 去掉 `收藏` 与 `生活 Tab`。

### F6: 下拉拉伸与 iOS 风格统一

- 个人主页顶部背景图默认高度为屏幕高的 `1/4`。
- 下拉时允许背景图最大拉伸到屏幕高的 `1/3`，松手后需要有回弹效果。
- 拉伸对象是完整 profile 头部，而不是只缩放背景图：
  - 背景图
  - 用户头像与资料区
  - 一级 Tab
  - 当前一级 Tab 下的列表起始位置
- 用户资料区顶部必须始终锚定在背景图底边，不允许出现“背景图在拉伸，但资料区没有下移”或“资料区下沉到背景图底边以下”的断层。
- 一级 Tab 下的内部列表不能再误触发头图拉伸。
- 个人主页整体升级到统一 iOS 风格：优先使用 Cupertino 风格按钮、分段、底部动作和图标语义。

### F7: 整页上卷与双阶段吸顶

- 上滑时应表现为整页整体上移，而不是背景、资料区、Tab、列表各自独立滚动。
- 在头像触顶前，背景图、头像、用户名、资料区、一级 Tab 和列表必须处于同一主滚动坐标系。
- 当头像底部越过顶部工具栏区域时，顶部工具栏进入紧凑态，显示小头像和用户名。
- 当一级 Tab 滚动到顶部工具栏下沿时，一级 Tab 吸顶固定在工具栏下方。
- 二级 Tab 不进入壳层吸顶体系，只属于各一级 Tab 的内容区，并随列表滚动；回滑到对应区域时必须自然回显。

### F8: metadata / codegen / 端云同步

- 用户域需要正式定义 `SubAccountProfileView`、`ProfileInheritanceStateView`、`RelationshipCapabilityView`。
- 内容域需要正式定义 `ProfileInteractionActivityView`，统一 `赞 / 评论 / 转发` 的互动活动语义。
- `_shared` 需要补齐 route、request_context，以及个人主页 tab/filter 的 UI 配置真相源。
- `user_profile/ui_config.yaml` 需要补齐头图几何参数与滚动/吸顶策略真相源，至少可表达：
  - `header_base_height_ratio = 0.25`
  - `header_max_stretch_ratio = 0.333`
  - `avatar_overlap_ratio = 0.333`
  - `compact_identity_bar`
  - `primary_tab_sticky_below_toolbar`
  - `secondary_tab_inline_scroll`
- App 侧 repository/provider/UI 必须改为消费新的 codegen 视图与常量，不再依赖手写 map 协议。

## 不做什么（Out of Scope）

- **O1**: `subAccount` 管理页完整重构；本 Story 只定义同步提示与主页消费的身份模型。
- **O2**: 统计详情页、共鸣页、圈子推荐算法的全面重做。
- **O3**: `same_interest / close_friend` 的完整产品化。
- **O4**: 新增独立 BFF 或聚合网关层承接个人主页。
- **O5**: Web/Desktop 端适配。

## 约束

- 以 `spec-first + metadata-first` 为前置，不允许先改 UI 再倒推契约。
- 保留现有 `/user/{username}` 路由形态，避免外部分享链接漂移。
- 允许兼容现有 `Persona` 记录命名，但新设计语义统一以 `SubAccount` 解释；兼容路径必须写明退出条件。
- 互动流的领域归属以内容域为主，用户域负责主页主体与关系能力，不在本 Story 内把所有互动读模型强行搬到 user-service。
- 滚动与吸顶交互必须建立在单一主滚动坐标系之上，不允许通过多个相互独立的 scroll view / offset 叠加去“拼”出头部动效。

## 对标输入与吸收结论

### 抖音 / 小红书个人主页

| 维度 | 对标做法 | 吸收结论 |
|------|---------|---------|
| 头像侵入头图 | 头像上侵、名字与资料主体分层 | 吸收 |
| 一级 Tab 吸顶 | 顶部吸顶、选中态清晰 | 吸收 |
| 二级胶囊筛选 | 左对齐、轻量切换 | 吸收 |
| 互动类型 | 点赞/评论/转发按内容动作组织 | 吸收 |
| 资料编辑同步 | 大多没有多身份同步 | 需要按本产品 owner/subAccount 模型自定义 |

### 内部对标

- 首页一级 Tab：复用 `CenteredScrollableTabBar` 的交互语义。
- 圈子页二级胶囊：复用 `SecondaryCapsuleTabBar` 的视觉语义。
- `comment-thread`：复用评论流在内容域的分页、身份展示和弱网处理经验。
- `user-service-cloud-delivery`：复用 user-service 的 DDD 分层、错误码、测试分层和交付约束。

## 非功能目标

- 端云契约单一真相源，不再出现 `Persona` 路由、`SubAccount` 路由和 UI 文案三套漂移。
- 个人主页首屏与折叠滚动行为在弱网和回弹场景下稳定，不出现“背景缩放但 profile 不下拉”的结构性错误。
- 下拉拉伸、整体上卷、头像吸顶与一级 Tab 吸顶的阈值可由统一配置推导，不依赖散落在 UI 内的魔法数。
- 资料编辑同步链路可灰度、可观测、可回滚。

## 验收重点

1. owner/subAccount 一体化主页模型与写入同步契约已经冻结为 metadata 真相源。
2. 用户域与内容域对主页的职责边界清晰，关系能力与互动活动不再混在同一个手写 DTO 中。
3. 端侧可基于新 DTO/常量收敛到统一 `ProfileShell`，进入 `/dev` 后不再需要重新裁决 IA。
4. 整页下拉拉伸、整体上卷、头像/名称吸顶、一级 Tab 吸顶与二级 Tab 回显行为已经冻结为可开发规格。
