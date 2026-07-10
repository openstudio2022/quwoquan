# L3 Story：圈子主页交集重做

## 节点定位

- `L1_domain_service`: `object-homepage-network`
- `L2_business_capability`: `intersection-unified-experience`
- `L3_story`: `circle-homepage-intersection-redesign`

## 功能说明

圈子主页（`CircleShell`）与「我的主页/他人主页」同壳同语义 token 重做，统一结构为「身份 → 我的交集 → 圈子打动的人 → 记录·讨论·成员」。规格真相源见 [intersection-definition-and-application.md](../../../../product/intersection-definition-and-application.md) §17.7 与 §17.8（双模块口径）。两个核心维度：

- **我的交集 = 我与这个圈子客观存在、可枚举、可解释、可行动的真实连接点**（圈子里你认识的人、你已加入/讨论过、你关注的话题在这里）。
- **圈子打动的人 = 这个圈子帮助他人产生连接、内容传播、讨论沉淀的能力**，同样可证、可枚举、可解释、可行动；`impact` 仅保留为内部机器名。

## 范围

- 我的交集卡：标题统一为「我的交集」，与我的主页同壳，渲染共享 `ObjectIntersectionPreviewCard`（objectBType=circle、`objectSharedReasonsProvider` 单一真相源）：单列预览句（蓝色可点击锚点）+ 弱入口「查看全部」；可见结论只读 `IntersectionReason.primaryText/primarySpans`，禁止用 `EvidenceGroup` 或 `intersectionPoints` 本地拼主句。
- 打动卡：标题统一为「圈子打动的人」，`AuthorImpactCard` 同构（`IntersectionStatementCard` + `circleImpactProvider`），去好友化/去收藏；句内数字可下钻来源明细；无可枚举影响事实不展示。
- 头部：移除成员头像簇（你认识的人收敛进我的交集模块）；保留圈子独立头像（缺省回退封面）+「N 成员」单计数 + 认证标识。
- 核心动作：主按钮「加入圈子」，次按钮由「私信」改为「进入讨论」（切换到讨论 tab）。
- 一级 tab：`记录/讨论/成员`（metadata-first label_key）。
- 记录流：二级过滤（全部/图片/视频/长文）去胶囊改最右侧过滤图标；网格改双列瀑布；卡内唯一交集句（封面→交集句→标题→作者→赞）。
- 清理：删除 `section_interaction`/`circle_stats_row` 死代码与硬编码中文字面量（统一语义 token）。
- 用户语言禁词：移除「实体/Entity/Circle/为什么推荐」，`42个实体正在被讨论` → `42个话题正在被讨论`。

## Out of Scope

- 云侧 Circle 服务/排序/图谱实现（仅 metadata 契约预留 + alpha mock）。
- 圈子「私信」1v1 链路改造（保留现默认公共群聊入口）。

## 验收标准概要

- A1：我的交集卡走共享 `ObjectIntersectionPreviewCard`（objectBType=circle）单一真相源，标题「我的交集」，单列预览句（蓝锚点）+「查看全部」；无交集三态降级不占位。
- A2：打动卡标题「圈子打动的人」，与 `AuthorImpactCard` 同构，文案去好友化/去收藏，无影响事实不展示。
- A3：头部移除成员头像簇、保留圈子独立头像（缺省回退封面）+「N 成员」单计数；次按钮「进入讨论」。
- A4：一级 tab 显示「记录」；记录流二级过滤在最右侧、非胶囊；双列瀑布；卡内有且仅一条交集句。
- A5：删除 `section_interaction`/`circle_stats_row` 死代码与中文字面量；无禁用术语外露（为什么推荐/影响力泛词→我的交集/圈子打动的人模块标题）。
