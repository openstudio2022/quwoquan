# L3 Story：实体主页交集重做

## 节点定位

- `L1_domain_service`: `object-homepage-network`
- `L2_business_capability`: `intersection-unified-experience`
- `L3_story`: `entity-homepage-intersection-redesign`

## 功能说明

实体主页（`HomepageDetailShell`，school/place/enterprise/sight 归一 `homepageDetail`）与「我的主页/他人主页」同壳同语义 token 重做，统一结构为「身份 → 我的交集 → 影响力 → 关于这里 → 记录·讨论·相关圈子」。规格真相源见 [intersection-definition-and-application.md](../../../../product/intersection-definition-and-application.md) §17.7 与 §17.8（双模块口径）。两个核心维度：

- **我的交集 = 我与这里客观存在、可枚举、可解释、可行动的真实连接点**（你认识的人在这里、你来过、你关注的话题在这里发生）。
- **影响力 = 这里帮助他人产生连接、内容传播、讨论沉淀的能力**，同样可证、可枚举、可解释、可行动。

用户语言只出现「这里/学校/景区/地点/公司/产品」，不外露「实体/Entity/为什么推荐」。

## 范围

- 我的交集卡：标题统一为「我的交集」，与我的主页同壳，渲染 `ObjectIntersectionPreviewCard`（共享积木，objectBType=homepage、`objectSharedReasonsProvider` 单一真相源）：单列预览句（蓝色可点击锚点）+ 弱入口「查看全部」；可见结论只读 `IntersectionReason.primaryText/primarySpans`，禁止用 `EvidenceGroup` 或 `intersectionPoints` 本地拼主句；无真实交集时克制空态不占位。
- 影响力卡（新增）：标题「影响力」，与「我的影响力」（`AuthorImpactCard`）/圈子影响卡同构，渲染 `IntersectionStatementCard` + `entityImpactProvider`；逐条只读云侧 `EntityImpactItem.primaryText/primarySpans`，句内数字可点击下钻「影响明细」sheet（来源摘要 + 样本视觉）；无可枚举影响事实时不展示，不用主观营销语。
- 关于这里卡：标题「关于这里」；正文 2~4 行 + 缩略图；「查看更多介绍」进介绍详情页（下沉到双模块之下）。
- 核心动作：主按钮「关注」，次按钮由「私信」改为「发记录」（围绕这里沉淀记录）；移除首屏常驻「想去·正在去·结伴」入口（不再首屏占位）。
- 一级 tab：`记录/讨论/相关圈子`（metadata-first label_key）。
- 记录流：双列瀑布 + `PostPreviewCard`；卡内统一为 封面 → 交集句（蓝锚点）→ 标题 → 作者 → 赞；卡内唯一交集句；数据来自 `HomepageContentPreview`（alpha mock 提供 `intersectionReasons`，云侧预留）。
- 二级过滤：右侧漏斗入口 + ActionSheet（非胶囊）；过滤项进 metadata `homepage_sub_tabs`。
- 相关圈子：可点击圈子卡，展示圈名、成员数、一句关联说明与「打开圈子」动作，点击进入圈子主页；无封面字段时使用语义图标兜底，不伪造封面/加入态。
- 头部：头像簇 +「N 关注」单计数；`verified` + 成立年份字段（契约预留 + alpha mock）。
- 公开信息：用户侧 fallback overview 只保留口碑、位置、分类、年份、下线说明等用户语义；`统一对象键/对象页模板/来源/认领状态/灰度 cohort/主页管理` 仅能在 owner/admin 操作入口表达，不得进入公开 tab。

## Out of Scope

- 云侧 Homepage/Entity 服务、排序、图谱实现（仅 metadata 契约预留 + alpha mock，含 `GetEntityImpact`/`ListEntityImpactEvidence` 端契约定义，Go handler 暂缓）。
- AB / 特征 / 召回系统。

## 验收标准概要

- A1：我的交集卡走 `ObjectIntersectionPreviewCard`（objectBType=homepage）单一真相源，标题「我的交集」，单列预览句（蓝锚点）+「查看全部」；无交集三态降级不占位。
- A2：影响力卡标题「影响力」，逐条只读云侧 `EntityImpactItem`，句内数字可下钻「影响明细」；无可枚举影响事实不展示，无主观营销语。
- A3：关于这里卡标题「关于这里」，正文 2~4 行 + 缩略图 +「查看更多介绍」进详情页；下沉到双模块之下。
- A4：核心动作主按钮「关注」、次按钮「发记录」；首屏不再常驻「想去·结伴」入口。
- A5：一级 tab 显示「记录/讨论/相关圈子」；记录流双列瀑布；二级过滤在最右侧、非胶囊；卡内有且仅一条交集句；相关圈子以可点击卡片进入圈子主页。
- A6：头部头像簇 +「N 关注」单计数 + 认证标识 + 成立年份；公开用户路径不展示内部运维字段；owner/认领/上报只从右上角更多菜单触达；无禁用术语外露（实体/为什么推荐→这里/我的交集）。
