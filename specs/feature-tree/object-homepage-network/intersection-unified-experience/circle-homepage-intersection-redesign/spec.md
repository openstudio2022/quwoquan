# L3 Story：圈子主页交集重做

## 节点定位

- `L1_domain_service`: `object-homepage-network`
- `L2_business_capability`: `intersection-unified-experience`
- `L3_story`: `circle-homepage-intersection-redesign`

## 功能说明

圈子主页（`CircleShell`）沿用他人主页同壳同口径重做交集体验与记录流，统一结构为「身份 → 为什么推荐这个圈子 → 这个圈子帮助了很多人 → 记录·讨论·成员」。规格真相源见 [intersection-definition-and-application.md](../../../../product/intersection-definition-and-application.md) §17.7。

## 范围

- 交集卡标题：`与你的交集` → `为什么推荐这个圈子` 列表入口（结论句 + 辅助说明 + 查看更多，主谓宾单句）；可见结论只读 `IntersectionReason.primaryText/primarySpans`，禁止用 `EvidenceGroup` 或 `intersectionPoints` 本地拼主句。
- 价值卡：自建影响力卡收敛为 `AuthorImpactCard` 同构，标题 `这个圈子帮助了很多人`，去好友化/去收藏。
- 一级 tab：`内容 → 记录`（metadata-first，新 label_key，不连带实体页）。
- 记录流：二级过滤（全部/图片/视频/长文）去胶囊改最右侧过滤图标；网格改双列瀑布；卡内唯一交集句。
- 头部：头像簇 +「N 成员」单计数；圈子独立头像字段（契约预留 + alpha mock，缺省回退封面）；认证标识沿用。
- 用户语言禁词：移除「实体/Entity/Circle/交集/影响力」，`42个实体正在被讨论` → `42个话题正在被讨论`。

## Out of Scope

- 云侧 Circle 服务/排序/图谱实现（仅 metadata 契约预留 + alpha mock）。
- 圈子「私信」1v1 链路改造（保留现默认公共群聊入口）。

## 验收标准概要

- A1：交集卡标题为「为什么推荐这个圈子」，列表入口每行单结论句 + 至多一条辅助说明 + 查看更多。
- A2：价值卡标题「这个圈子帮助了很多人」，与 `AuthorImpactCard` 同构，文案去好友化/去收藏。
- A3：一级 tab 显示「记录」；记录流二级过滤在最右侧、非胶囊；双列瀑布；卡内有且仅一条交集句。
- A4：头部头像簇 +「N 成员」单计数；圈子独立头像（缺省回退封面）；无禁用术语外露。
