# L2 能力：交集统一体验与推荐

## 节点定位

- `L1_domain_service`: `object-homepage-network`
- `L2_business_capability`: `intersection-unified-experience`

本能力把"交集"从当前的 demo 占位（问小趣 dock + 端拼整句 + 大关注按钮 + 无头像/无名字）收口为一套端云一体、事实与概率分通道、带保鲜期与推荐冷却窗口、统一视觉的对象交集网络。它统一驱动六个应用场景 + 一个横切句型规范：

| 场景 | L3 Story | 核心 surface |
|---|---|---|
| S1 首页推荐 | `home-recommend-intersection-redesign` | feed 卡 + spotlight |
| S2 他人主页 | `user-profile-intersection-redesign`（他人） | 为什么推荐TA |
| S2 我的主页 | `user-profile-intersection-redesign`（我的） | 我的连接 / 我的影响力 |
| S3 实体主页 | `entity-homepage-intersection-redesign` | 我的交集 + 影响力 |
| S4 圈子主页 | `circle-homepage-intersection-redesign` | 我的交集 + 影响力 |
| S3/S4 端云闭环 | `object-homepage-gamma-real-data-closure` | gamma-local 真实 bundle / impact / object intersections |
| S5 全局搜索 | `search-intersection-consumption` | 交集 Tab + 发现区分组 |
| 横切 | `intersection-sentence-unification` | primaryText 单句 + G2 |

规格真相源：`specs/product/intersection-definition-and-application.md` §17–§18。

前台不出现"交集网络""事实通道""概率通道"等工程术语；用户只感知"你们的交集""你和这里的交集""你认识的人在这""与你有交集的人和内容"。

## 背景与动机

1. 我的主页交集入口缺失，首屏被 demo 式"问小趣"占位，用户无法看到"现在有多少人/对象和我有交集"。
2. 他人/实体主页交集卡已能展示，但与"问小趣"demo dock 同屏，dock 三个 pill 回调全为 null，是无行为占位。
3. 首页交集推荐卡（`UnifiedObjectCard`）用整句 `displayText` + 大关注按钮 + 图标占位（无真实头像/名字），视觉粗糙、不达商用标准。
4. 校园、旅行频道虽已具备 spotlight 策略，但缺交集数据，前台无频道专属交集。
5. 交集理由后端硬编码占位；事实交集（`ObjectIntersection`/`ObjectMembership`）与概率交集（`RecommendationAffinity`）契约已定义但零消费；无保鲜期、无跨会话推荐冷却窗口、无曝光→点击→转化完整漏斗。

## 商用目标

- 事实可信：每条用户可见交集都有可理解、可回查、满足权限的证据；算法只用于排序，不伪装事实。
- 行动明确：每条交集引导清晰行动（关注、加入、查看共同内容、进入对象页）。
- 界面克制：减少解释性文案，用头像、名字、维度 chip、计数 badge 传达，去掉大关注按钮。
- 可运营：交集曝光、点击、转化、清零全链路埋点，按 cohort 可观测、可回滚。
- 高并发且准确：事实交集预物化、请求期零打分；概率交集批量打分 + 缓存；冷却/保鲜 O(logN) 过滤。

## 交集维度（闭集，复用 `IntersectionReason.dimension` 5 源）

| 维度 | 含义 | 类别 | 锚点真相源 |
|---|---|---|---|
| `identity` 身份 | 同校/校友/同乡/同司 | 事实 | `ObjectMembership` + identity `tagRef` |
| `location` 地点 | 到过同一地点/同游 | 事实 | geo `tagRef`（不暴露精确实时位置） |
| `content` 内容 | 共看/共评/共创/共转 | 事实 | 行为边 |
| `relationship` 关系 | 共同好友/互关/被同一人关注 | 事实 | follow/contact 边（默认头像簇） |
| `interest` 兴趣 | 事实兴趣：共同显式标签、共同兴趣圈子 | 事实 | `tagRef` + circle membership |
| `interest` 兴趣 | 概率兴趣：算法相似"可能合得来/推荐认识" | 概率 | `RecommendationAffinity`（不造证据） |

## 事实 vs 概率（两通道）

- 事实交集 = `ObjectIntersection`（带 `evidenceItems`、`confidenceLabel`、`computedAt`/`expiresAt`）：可直接计算/查询，请求期不打分。
- 概率交集 = `RecommendationAffinity`（`score`/`modelReasonBucket`/`experimentBucket`）：走 `/v1/score`，端侧明确标注"推荐"，文案不伪装事实。
- 合并排序：事实优先（`strength` + 新鲜度），概率其次（`score`）；统一经过推荐窗口/冷却过滤。

## 入口 × 维度 × 展示 × 性能 × 验收 矩阵

| 入口 | 交集维度 | 如何展示 | 性能算法与处理 | 验收标准 |
|---|---|---|---|---|
| 我的主页「我的交集」聚合入口 | 5 维全量 | 总数 + 最多 3 个维度变化红点/数字；超 3 维度收起「展开更多」；点进按维度分组列表页展示"自上次查看新增"；打开列表即推进已读水位并清零红点（不需逐项查看详情） | 读模型 `viewer_object_intersections` 增量物化 + `cache:viewer_intersections:{userId}`；未读 = `computedAt > watermark`；分页 cursor | 3 秒看清"谁/哪个维度有新交集"；打开即清零；空态用用户语言 |
| 他人用户主页「你们的交集」 | 事实全维 | 交集卡：头像 + 名字 + 维度短标签 + 证据微缩；无大按钮，点卡进对象页 | bundle 优先；回退 `objectSharedReasonsProvider` | 每条有 evidence；3 秒可读；无 demo dock |
| 实体主页「你和这里的交集」 | 事实全维 | 同上，bundle 优先 | bundle `intersections` 后端填充 | 同上 |
| 圈子主页「你认识的人有 N 个在这」 | relationship/identity 事实 | 新增交集卡 + 成员头像簇 | bundle/list 查询 | 圈子页出现交集卡；点头像进用户页 |
| 首页推荐 tab + 频道（recommend/campus/travel/tech/car） | 事实 + 概率混排 | `IntersectionSpotlight`：去关注按钮、真实头像 + 名字、共同点安静 chip、模块头「N 位与你有交集」红数字；首页 ≤4 卡、频道 ≤3 卡 | 事实读模型 + 概率打分混排；过保鲜期/冷却不再出现；按 channel 下发对应交集 | campus/travel 出专属交集；曝光未转化窗口内不重复；视觉统一 |
| 全局搜索「交集」Tab + 发现区分组 | 事实 + affinity（发现区） | 每张卡一条 `primaryText`；分组消费 `connectionState`；已连接区不展示交集句 | search hit 携带 `intersectionReason` 子集 + `connectionState` | 交集 Tab 非空（alpha mock）；G2 零端拼 |
| 关注列表 strip | 关注对象动态 | 沿用已有未读红点机制（不改交集语义） | `following_subject` lastVisited/unread | 不回退现有能力 |
| 小艺 | 消费 `ObjectPageContext` | 移除三处 demo dock；主动服务改"证据旁轻提示"（带 confidence/cooldown/dismiss） | 触发策略 + 冷却 | 0 demo 语言；不遮挡主操作 |

## 推荐保鲜期与冷却窗口

- 保鲜期：事实 `expiresAt`（membership/identity 长、location/content 短）；过期触发重算。
- 推荐窗口/冷却：曝光未转化 → 写 `rec:icool:{userId}`（Redis sorted set，member=objectId、score=expireAt），默认 14 天、`policy.yaml` 可配；跨会话持久（区别于现有会话级 30min `rec:exposed`）；查询 `ZRANGEBYSCORE` 排除。

## Out of Scope

- 不新增交易/支付/预约闭环。
- 不新增第二套标签枚举；标签真相源仍为 `publish/tags` + metadata `tagRef`。
- 不保留端侧拼接交集整句、旧 demo dock、`TodayIntersectionRail` 死代码分支。

## 验收重点

1. 我的主页交集聚合入口可用：总数 + ≤3 维度红点 + 自上次新增列表 + 打开清零。
2. profile/entity/circle 三类主页 0 demo dock。
3. 首页交集卡去关注按钮、头像 + 名字 + 红计数；首页 ≤4、频道 ≤3。
4. campus/travel 频道出现专属交集推荐。
5. 事实/概率分通道，事实每条可追溯，概率明确标注推荐。
6. 保鲜期/冷却窗口生效；曝光→点击→转化全链路埋点。
7. 页面横向质量 P1-P8、Mock 隔离、语义 token、弱类型预算、local_contract-user_acceptance 全部满足。
8. 实体主页与圈子主页的 gamma-local 真实数据闭环必须通过 `object-homepage-gamma-real-data-closure`；本地 UI 通过不等同于商用成熟。

## 架构基线 v2 对齐（§21 收口，A–E 五会话开工基线）

> 真相源：`specs/product/intersection-definition-and-application.md` §21。本节是 L2 能力对该基线的承接，不另起真相源。

### 三层统一模型（采集 → 算法 → 投影）

交集是一条「加权社交图谱边」在管线上被赋予四层属性：

- **Graph 结构**：节点=`person|circle|content|place|enterprise|school|tag`；边=27 个 kind 升级为加权有向边，`edgeWeight = relationStrength × interactionFrequency × recencyDecay`。映射既有 SharedFact/BridgeFact（可证边）+ Affinity（概率边）。
- **Lifecycle 变化**：边状态机 `new → strengthened → stable → weakened → reactivated`；仅作弱标/红点，不进 `primaryText`。既有 `fresh/seen + newCount` 仅覆盖 `new`，其余四态分期真算。
- **Propagation 扩散**：影响从单跳计数升级为可证路径（人→人 / 人→圈子 / 人→内容→人）；端只展示可证绝对计数 + 路径节点，禁 reach/conversion 比率。
- **Projection 表达**：iconKey + primaryText/spans + visuals + target + lifecycle 弱标。

### 端侧展示统一（具象化四槽，本期重点）

单行交集卡 = `[① 类型图标 iconKey] + [② 句内 inline 头像簇] + [③ 尾部对象封面] + [④ lifecycle 弱标]`。

- iconKey 语义闭集（§21.5.2）：`place|circle|people|alumni|work|discussion|share|like|interest`（交集）/ `connect|circle|discussion|compass|read|share`（影响）；端 `IntersectionIconResolver` 解析，禁端硬编码 switch。
- 密度上限：紧凑 surface 1 句、lifecycle 仅「新」；列表入口 1 结论句 + ≤1 灰色辅助；对象页证据组一屏 ≤5。
- 降级链：具名样本+头像 → 纯计数 → 维度母表达 → 隐藏。

### 五面展示统一矩阵（A–E）

| 面 | 主表达 | 具象化要点 |
|---|---|---|
| A 我的主页 | 我的连接（lifecycle 分桶弱标）+ 我的影响力（传播视图） | 四槽样板首落；author_impact 路径节点 + secondarySpread 计数 |
| B 用户主页(他人) | 为什么推荐TA + TA的影响力 | 证据组叠 lifecycle 弱标 + 句内头像 |
| C 实体主页 | 我的交集 + 影响力 + 记录流单句 | 复用 ObjectIntersectionSection；对象封面缩略图；影响数字可枚举来源 |
| D 圈子主页 | 我的交集 + 影响力 | circle_impact 接统一三件套（解决 G4）+ 成员/讨论/记录可追溯 |
| E 首页 post | post 卡内单句 chip | 紧凑：1 句 + lifecycle 仅「新」，不堆叠 |

### 赞红线翻转（§21.9）

`coLiked`（赞）恢复为 user_acceptance 最低权重轻量交集事实；只翻赞、不恢复收藏（§14A favorite 退场不变）；性能上禁请求期全量求交，走预投影/采样/上限。

### 分期边界

- 本期（契约草案 + 端原型）：metadata 草案字段 + `codegen-app` 端 DTO + 端共享组件/Mock/A–E UI 原型 + 端测试。契约标「草案/未冻结」。
- 后置（云侧）：数据源采集、Graph 加权真算、Lifecycle 状态机、多跳 Propagation、coLiked 预投影、Selection 数值化、Remote 填充。
