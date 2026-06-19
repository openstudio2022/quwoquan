# L3 Story：实体主页交集重做

## 节点定位

- `L1_domain_service`: `object-homepage-network`
- `L2_business_capability`: `intersection-unified-experience`
- `L3_story`: `entity-homepage-intersection-redesign`

## 功能说明

实体主页（`HomepageDetailShell`，school/place/enterprise/sight 归一 `homepageDetail`）沿用他人主页同壳同口径重做交集体验与记录流，统一结构为「身份 → 为什么推荐这里 → 关于这里 → 记录·讨论·相关圈子」。规格真相源见 [intersection-definition-and-application.md](../../../../product/intersection-definition-and-application.md) §17.7。用户语言只出现「这里/学校/景区/地点/公司/产品」，不外露「实体/Entity」。

## 范围

- 交集卡：由 bundle 直出改为 `ObjectIntersectionSection`（objectBType=homepage）单一真相源，标题 `为什么推荐这里`（结论句 + 辅助说明 + 查看更多，主谓宾单句）。
- 关于这里卡：标题 `认识XX` → `关于这里`；正文 2~4 行 + 缩略图；「查看更多介绍」进介绍详情页。
- 一级 tab：`内容/讨论/兴趣圈 → 记录/讨论/相关圈子`（metadata-first label_key）。
- 记录流：单列 → 双列瀑布 + `PostPreviewCard`；数据从 `HomepageContentPreview` 升级为可渲染 `PostBaseDto` 流（alpha mock 提供，云侧预留）；卡内唯一交集句。
- 二级过滤（当前缺失，新建）：右侧漏斗入口 + ActionSheet（非胶囊）；过滤项进 metadata `homepage_sub_tabs`。
- 头部：头像簇 +「N 关注」单计数（"同趣"→事实"关注"）；补 `verified` + 成立年份字段（契约预留 + alpha mock）；基础信息行补年份。

## Out of Scope

- 云侧 Homepage/Entity 服务、排序、图谱实现（仅 metadata 契约预留 + alpha mock）。
- AB / 特征 / 召回系统。

## 验收标准概要

- A1：交集卡走 `ObjectIntersectionSection` 单一真相源，标题「为什么推荐这里」，列表入口每行单结论句 + 至多一条辅助说明 + 查看更多。
- A2：关于这里卡标题「关于这里」，正文 2~4 行 + 缩略图 +「查看更多介绍」进详情页。
- A3：一级 tab 显示「记录/讨论/相关圈子」；记录流双列瀑布；二级过滤在最右侧、非胶囊；卡内有且仅一条交集句。
- A4：头部头像簇 +「N 关注」单计数 + 认证标识 + 成立年份；无禁用术语外露（实体→这里/话题）。
