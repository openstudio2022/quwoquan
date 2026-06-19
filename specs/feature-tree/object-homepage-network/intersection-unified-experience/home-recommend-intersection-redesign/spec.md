# L3 Story：首页推荐交集重做

## 节点定位

- `L1_domain_service`: `object-homepage-network`
- `L2_business_capability`: `intersection-unified-experience`
- `L3_story`: `home-recommend-intersection-redesign`

## 功能说明

按高保重做首页推荐页的交集体验：feed 卡片卡内唯一一条蓝色主谓宾交集句；「与你有关的新发现」横滑 spotlight 收敛为单句主谓宾。规格真相源见 [intersection-definition-and-application.md](../../../../product/intersection-definition-and-application.md) §17.4。

## 范围

- feed 卡片（双列瀑布 `DualColumnDiscoveryPostCard` / 单列 `_HomeRelationPostCard`）：卡内唯一交集句。
- spotlight 模块（`IntersectionSpotlightModule`）：头像/封面 + 类型角标 + 一条主谓宾句（替换主/副双句堆叠）。
- 保留交集句点击进对象页高亮归因（§7.3 旅程锚）。

## Out of Scope

- 频道集合调整（财经 vs 车友留 metadata 后续）。
- 云侧推荐排序 / 保鲜冷却实现。

## 验收标准概要

- A1：每张 feed 卡片卡内有且仅一条交集句。
- A2：spotlight 卡为单句主谓宾，无主/副双句堆叠。
- A3：点击交集句进对象页保留高亮归因不回归。
