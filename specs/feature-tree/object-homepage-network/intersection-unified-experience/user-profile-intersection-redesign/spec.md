# L3 Story：他人/我的主页交集重做

## 节点定位

- `L1_domain_service`: `object-homepage-network`
- `L2_business_capability`: `intersection-unified-experience`
- `L3_story`: `user-profile-intersection-redesign`

## 功能说明

他人主页与我的主页同壳（`ProfileShell`）同步重做交集体验与头部信息架构，对齐高保。规格真相源见 [intersection-definition-and-application.md](../../../../product/intersection-definition-and-application.md) §17.4。

## 范围

### S2a 他人主页（Others）

- 公共头部：认证标识 + 摘要区挂载统计行（记录/粉丝/关注/获赞）。
- 一级 tab：`内容 → 记录`；二级过滤改最右侧过滤项/图标，去胶囊。
- `我与TA的交集` 列表入口（结论句 + 辅助说明 + 查看更多）。
- `TA的影响力` 去好友化文案（历史「TA帮助了很多人」口径在 V5 废止）。

### S2b 我的主页（Mine）

- 同壳头部与 tab/过滤规则与 S2a 一致。
- `MyIntersectionInboxCard` 升级为 `我的连接` 列表入口（红点聚合并入「查看更多」）。
- `我的影响力` `isMine` 视角，去好友化/去收藏。

## Out of Scope

- 圈子主页、实体主页（后续 story）。
- 云侧 viewer_object_intersections 读模型实现。

## 验收标准概要

- A1：他人/我的主页头部均含认证标识 + 4 列统计行。
- A2：一级 tab 显示「记录」；二级过滤在最右侧、非胶囊。
- A3：`我与TA的交集` / `我的连接` 为列表入口，每行单结论句 + 至多一条辅助说明。
- A4：影响力文案去好友化（`认识了新朋友` → `建立了新连接`），无收藏文案。
