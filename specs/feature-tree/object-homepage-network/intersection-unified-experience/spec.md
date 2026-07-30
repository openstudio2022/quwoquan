# L2 Business Capability：交集统一体验与推荐 (`intersection-unified-experience`)

> 所属领域：[`object-homepage-network`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

以统一的交集事实、置信度、保鲜期和展示契约驱动发现、对象主页、圈子、聊天、个人主页与助理场景

## 2. 范围与非目标

### In Scope

- 六场景（S1–S5 + 横切句型）primaryText 单句展示与 G2 门禁。
- 我的主页「我的交集」聚合入口：总数 + 最多 3 维度红点 + 自上次新增列表 + 打开清零。
- profile/entity/circle 三类主页移除 demo 问小趣 dock。
- 全局搜索交集 Tab 与 connectionState 分组消费 intersectionReason 子集。
- 首页与各频道（含校园、旅行）交集推荐卡重设计：去关注按钮、头像 + 名字 + 红计数。
- 实体主页与圈子主页的 gamma-local 真实 bundle、impact、related groups、object intersections 端云闭环。
- IntersectionReason 字段收敛、recommendation/intersection 域契约、viewer_object_intersection 读模型。
- 事实与概率分通道、保鲜期、跨会话推荐冷却窗口、曝光到转化漏斗埋点。

### Out of Scope

- 交易、支付、预约闭环。
- 第二套标签枚举或端侧拼接交集文案。
- following_subject 关注列表未读机制改造。

## 3. Journey / Scenario 贡献

- [`JNY-011 / SCN-026`](../../spec.md#scn-026)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：以统一的交集事实、置信度、保鲜期和展示契约驱动发现、对象主页、圈子、聊天、个人主页与助理场景，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。

## 4. Story



- [`circle-homepage-intersection-redesign`](./circle-homepage-intersection-redesign/spec.md)：标题统一为「圈子打动的人」，文案口径与 `intersection_kind_registry.yaml` 登记的 kind / dimension / actionHint 口径一致。
- [`entity-homepage-intersection-redesign`](./entity-homepage-intersection-redesign/spec.md)：定义“实体主页交集重做”的可观察主路径、失败语义及父能力交接。
- [`home-recommend-intersection-redesign`](./home-recommend-intersection-redesign/spec.md)：spotlight 文案口径与 `intersection_kind_registry.yaml` 登记的 kind / dimension / actionHint 口径一致。
- [`intersection-algorithm-closure`](./intersection-algorithm-closure/spec.md)：ranking-signal-fusion spec 登记 intersection fact/affinity 权重入口。
- [`intersection-sentence-unification`](./intersection-sentence-unification/spec.md)：seed、服务响应与展示口径均与 `intersection_kind_registry.yaml` 及本 Story Display Contract 一致。
- [`object-homepage-gamma-real-data-closure`](./object-homepage-gamma-real-data-closure/spec.md)：metadata 与 compose 静态契约通过。
- [`user-profile-intersection-redesign`](./user-profile-intersection-redesign/spec.md)：他人/我的主页二级过滤同一实现。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 我的主页交集聚合入口与清零 SIT

- 我的主页展示交集总数与最多 3 个维度的变化红点/数字，超 3 维度可展开更多。
- 点击进入按维度分组列表页，展示自上次查看的新增交集。
- 打开列表即推进已读水位并清零红点，无需逐项查看详情。

<a id="req-002"></a>
### REQ-002 对象页交集卡与 demo dock 移除 SIT

- profile/entity/circle 三类主页不再出现问小趣 demo dock。
- 他人用户主页、实体主页、圈子主页展示事实交集卡，每条有可读证据。
- 圈子主页出现「你认识的人有 N 个在这」交集卡。

<a id="req-003"></a>
### REQ-003 首页与频道交集推荐重设计 SIT

- 首页交集卡去掉关注按钮，使用真实头像 + 名字 + 维度 chip + 安静共同点 chip。
- 模块头展示「N 位与你有交集」红数字；首页 ≤4 卡、频道 ≤3 卡。
- 校园、旅行频道出现频道专属交集推荐。
- travel 频道只消费 content metadata 生成的 `intersectionModulePolicy=spotlightSegment`，端侧不得维护频道专用 override。
- 事实交集明确证据，概率交集明确标注推荐，混排后统一排序。

<a id="req-004"></a>
### REQ-004 保鲜冷却与曝光转化漏斗 SIT

- 曝光未转化的交集对象在配置窗口（默认 14 天）内不再重复推荐。
- 事实交集带 computedAt/expiresAt，过期触发重算。
- 交集曝光、点击、转化、清零全链路携带 intersectionId/dimension/intersectionClass/cohort 进入行为管道。

<a id="req-005"></a>
### REQ-005 v3 可行动交集与商用主轴 SIT

- 交集触点统一遵循产品主轴「别人帮你刷内容，我们帮你遇到对的人」；所有可见交集句只读云侧 primaryText/primarySpans/displayBinding，端不拼句，join(spans.text)==primaryText 不变量成立。
- 上下文 SVO 成立：explicit_link 必须有 typed object span；host_implicit/host_plain 必须由当前内容卡/视频书/搜索 hit/主页宿主对象证明，禁止可点击 self-target 和 reason 池随机附着。
- 主句禁止 raw stats、泛对象和旧术语：不出现 `2赞1评`、`这条记录`、`TA的内容`、`相关圈子`、`我的连接`。
- 前台用户维度收敛为「交集 / 打动」两词，入口统一「交集配对」、收件箱统一「我的交集」
- “今日”只保留为最小时间粒度的次级说明，辐射他人用「打动」
- 旧「兴趣配对 / 找同趣 / 今日同趣机会 / 影响力」前台退场，机器标识 `interest_match` / `impact` 保留。
- 七触点（视频书/首页内容卡/用户主页/我的主页/圈子主页/实体主页/交集配对 launcher）密度与行动重心符合 `REQ-006` 的七触点统一矩阵；四主页复用 ObjectIntersectionSection/ObjectIntersectionCard，不新增第四套抽象。
- C0 差异化切片「共同想去→约伴」用已有 coWishlistedEntity + 关注 + 交集信号触发 start_gathering；safetyGate 未满足时优雅降级为查看证据/进入对象，无登录死循环。
- deferred 的附近/实时/线下局（coPresentHere/nearbyAffinity/meet_nearby/gatheringDetail）不出现在正式可执行 UI；交集配对 launcher 不渲染伪候选。
- 北极星为可行动交集完成/关系形成（非 DAU），护栏反指标（骚扰率/拒绝率/举报率）与漏斗（曝光→证据展开→行动→完成→关系形成→回流）可观测。
- 垂类扩展只走 [L2 DEC-002](./design.md#dec-002) 的四件套（`vertical` 值 + `objectKind` + taxonomy 子树 + 事实生产者），禁止新增 kind / dimension / actionKey，禁止端侧垂类分支；同一批端侧断言在换垂类后无需改端侧代码。

<a id="req-006"></a>
### REQ-006 合并排序：事实优先（strength + 新鲜度），概率其次（score）；统一经过推荐窗口/冷却过滤

- 合并排序：事实优先（`strength` + 新鲜度），概率其次（`score`）；统一经过推荐窗口/冷却过滤。
- **七触点统一矩阵**（密度 + 行动重心，本条即唯一口径）：视频书底部单句 / 首页紧凑 chip / 用户主页证据组 / 我的主页收件箱 / 圈子主页证据卡 + 成员簇 / 实体主页证据卡 + 记录单句 / 交集配对 launcher（不产候选）。四主页表达仍复用 `ObjectIntersectionSection` / `ObjectIntersectionCard`，不新增第四套抽象。前台用户维度收敛为「交集 / 打动」、入口统一「交集配对」、收件箱统一「我的交集」；“今日”只作最小时间粒度的次级说明，机器标识 `interest_match` / `impact` 内部保留。
- 七触点端侧必须消费同一交集表达与对象页行动分发契约；云侧只下发 canonical `actionHint`。
- `IntersectionTargetNavigator.openActionHint` 按 `dispatch/targetAvailability` 分发，navigate/assistant 的 login 等门不在交集组件拦截，导航到承接页由承接页复用既有 gate + `AuthContinuation` 续接（口径见 `.cursor/rules/15-auth-entry-no-loop.mdc`），关注/加入/进入讨论/看共同来源等 login 门轻行动恢复可见可点（修复首版「login 门行动被系统性隐藏」P0）
- `message/companion/connect` 无真实卡内 handler 时诚实不显示、deferred 不执行，死参数 gateResolver/gated 已移除（R26）
- `ObjectIntersectionPreviewCard` 只能是 `ObjectIntersectionSection` 的薄包装；`start_gathering` 和 `message_person` 只有在真实承接页与权限门成立时才可展示。
- `safetyGate`、moment 意图时态和行动阶梯以 metadata 模型为准，所有主页和交集入口必须消费同一模型。
- 端云真实数据准出由 [`object-homepage-gamma-real-data-closure`](./object-homepage-gamma-real-data-closure/spec.md) 负责。

<a id="req-007"></a>
<a id="display-contract"></a>
### REQ-007 交集展示合同（Display Contract / §17）

> 仓内锚点：本条即历史文档所称「intersection-definition §17 / Story Display Contract」的唯一规格落点。
> 实现真相源仍是 `intersection_kind_registry.yaml#statementTemplates` 与
> `intersection_reason.yaml` 的 `primaryText` / `primarySpans` / `primaryTextL10nKey` /
> `displayBinding`；本条只规定可观察合同，不复制模板正文。

- **§17.1 结论句结构**：事实通道主句 =「主语[关系限定 + 代表人 + 人数] + 谓语[行为动词] + 宾语[typed object 或宿主上下文]」。
- 模板与 l10nKey 唯一登记在 `statementTemplates.byKind`，云侧一次渲染同时产出 `primaryText` 与 `primarySpans`，`join(spans.text) == primaryText` 结构性成立。
- 端只读直出，禁止本地拼句或按 kind 硬编码中文谓语。
- **§17.2 句式层次**：紧凑 surface（首页内容卡 / spotlight / 视频书）严格单句、不展示副句。
- 列表入口（我的交集 / 为什么推荐TA / 打动）才允许至多一条灰色 `secondaryText`。
- **降级链**：具名对象 → 纯计数句（仅登记了 `counted` 的 kind）→ 隐藏。缺名时禁止造名或借邻近语义。
- **分通道诚实**：`intersectionClass=fact` 必须可向用户说明证据。`affinity` 必须带 `confidenceLabel` 等推荐标注，禁止把概率推荐伪装成事实关系。
- **垂类正交（§23.4）**：扩展只改 `vertical` + `objectKind` + taxonomy 子树 + 事实生产者，禁止独立垂类 kind 名。口径与 [DEC-002](./design.md#dec-002) 一致。

<a id="req-008"></a>
### REQ-008 商用诚实红线与冷启动供给闸门（原 P0）

- **到访语义**：`coVisitedEntity` 只能由可证到访事实（`post.visitedAt` + 地点同一性）产出，结论句说「都去过」。
- 浏览行为归 `sharedEntityAttention`（「也看过」），意图归 `coWishlistedEntity`（「都想去」），三者不得互相替代。
- **行动承诺一致**：`actionHint` 的按钮文案必须与 `dispatch` / `targetAvailability` 真实可完成的副作用一致。
- `greet_person` 在打招呼状态机未接通前不得承诺「打招呼」却只 `navigate` 到主页——要么改文案要么改 dispatch。
- **冷启动供给闸门**：`Feed` / `ListMyIntersections` / `ObjectIntersections` 三入口共用 `coldStartSupply`。
- 某 kind 的候选池去重对象数低于 `minDistinctObjectsByKind` 时整 kind 不下发，防止 N=1 语料下「人人都有交集」稀释信息量。
- 探针不可用时供给判定 fail-open，但 deferred kind 永不 fail-open。

## 6. 契约与依赖

- 上游能力：[`object-homepage-network`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 我的主页交集聚合入口与清零 SIT

- GIVEN 执行“我的主页交集聚合入口与清零”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“我的主页交集聚合入口与清零”对应动作。
- THEN 我的主页展示交集总数与最多 3 个维度的变化红点/数字，超 3 维度可展开更多。
- THEN 点击进入按维度分组列表页，展示自上次查看的新增交集。
- THEN 打开列表即推进已读水位并清零红点，无需逐项查看详情。

<a id="sit-002"></a>
### SIT-002 对象页交集卡与 demo dock 移除 SIT

- GIVEN 执行“对象页交集卡与 demo dock 移除”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“对象页交集卡与 demo dock 移除”对应动作。
- THEN profile/entity/circle 三类主页不再出现问小趣 demo dock。
- THEN 他人用户主页、实体主页、圈子主页展示事实交集卡，每条有可读证据。
- THEN 圈子主页出现「你认识的人有 N 个在这」交集卡。

<a id="sit-003"></a>
### SIT-003 首页与频道交集推荐重设计 SIT

- GIVEN 执行“首页与频道交集推荐重设计”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“首页与频道交集推荐重设计”对应动作。
- THEN 首页交集卡去掉关注按钮，使用真实头像 + 名字 + 维度 chip + 安静共同点 chip。
- THEN 模块头展示「N 位与你有交集」红数字；首页 ≤4 卡、频道 ≤3 卡。
- THEN 校园、旅行频道出现频道专属交集推荐。
- THEN 事实交集明确证据，概率交集明确标注推荐，混排后统一排序。

<a id="sit-004"></a>
### SIT-004 保鲜冷却与曝光转化漏斗 SIT

- GIVEN 执行“保鲜冷却与曝光转化漏斗”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“保鲜冷却与曝光转化漏斗”对应动作。
- THEN 曝光未转化的交集对象在配置窗口（默认 14 天）内不再重复推荐。
- THEN 事实交集带 computedAt/expiresAt，过期触发重算。
- THEN 交集曝光、点击、转化、清零全链路携带 intersectionId/dimension/intersectionClass/cohort 进入行为管道。

<a id="sit-005"></a>
### SIT-005 v3 可行动交集与商用主轴 SIT

- GIVEN 执行“v3 可行动交集与商用主轴”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“v3 可行动交集与商用主轴”对应动作。
- THEN 交集触点统一遵循产品主轴「别人帮你刷内容，我们帮你遇到对的人」；所有可见交集句只读云侧 primaryText/primarySpans/displayBinding，端不拼句，join(spans.text)==primaryText 不变量成立。
- THEN 上下文 SVO 成立：explicit_link 必须有 typed object span；host_implicit/host_plain 必须由当前内容卡/视频书/搜索 hit/主页宿主对象证明，禁止可点击 self-target 和 reason 池随机附着。
- THEN 主句禁止 raw stats、泛对象和旧术语：不出现 `2赞1评`、`这条记录`、`TA的内容`、`相关圈子`、`我的连接`。
- THEN 前台用户维度收敛为「交集 / 打动」两词，入口统一「交集配对」、收件箱统一「我的交集」
- AND “今日”只保留为最小时间粒度的次级说明，辐射他人用「打动」
- AND 旧「兴趣配对 / 找同趣 / 今日同趣机会 / 影响力」前台退场，机器标识 `interest_match` / `impact` 保留。
- THEN 七触点（视频书/首页内容卡/用户主页/我的主页/圈子主页/实体主页/交集配对 launcher）密度与行动重心符合 `REQ-006` 的七触点统一矩阵；四主页复用 ObjectIntersectionSection/ObjectIntersectionCard，不新增第四套抽象。
- THEN C0 差异化切片「共同想去→约伴」用已有 coWishlistedEntity + 关注 + 交集信号触发 start_gathering；safetyGate 未满足时优雅降级为查看证据/进入对象，无登录死循环。
- THEN deferred 的附近/实时/线下局（coPresentHere/nearbyAffinity/meet_nearby/gatheringDetail）不出现在正式可执行 UI；交集配对 launcher 不渲染伪候选。
- THEN 北极星为可行动交集完成/关系形成（非 DAU），护栏反指标（骚扰率/拒绝率/举报率）与漏斗（曝光→证据展开→行动→完成→关系形成→回流）可观测。
- THEN 垂类扩展只走 [L2 DEC-002](./design.md#dec-002) 的四件套，`verticalExtensionContract` 的四条禁令由 `verify_intersection_kind_registry.py` 阻断，同一批端侧断言在换垂类后无需改端侧代码。

<a id="sit-006"></a>
### SIT-006 交集展示合同（Display Contract / §17）

- GIVEN 任一 fact kind 在 `statementTemplates.byKind` 有登记，且证据足以产出具名对象或 counted 降级句。
- WHEN 云侧 Explain 管线渲染该 reason。
- THEN `primaryText` 与 `primarySpans` 由同一模板产出，`join(spans.text) == primaryText`，并下发对应 `primaryTextL10nKey`。
- AND 紧凑 surface 不展示 `secondaryText`。
- AND affinity 带推荐标注。
- AND 未登记 kind 或证据不足时不下发展示句。

<a id="sit-007"></a>
### SIT-007 商用诚实红线与冷启动供给闸门

- GIVEN 浏览行为与声明到访行为同时存在于同一地点。
- WHEN 产出交集 reason。
- THEN 浏览只进 `sharedEntityAttention`，声明到访才进 `coVisitedEntity`，二者文案不得互换。
- AND `actionHint` 文案与 `dispatch` 承诺一致；供给低于阈值的 kind 在 Feed/List/ObjectIntersections 三入口均不下发。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 同趣匹配后端聚合与重行动风控

- 类型：`risk`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：同趣匹配缺少可信后端聚合、对象授权、骚扰防护和可审计重行动门禁。
- 完成判定：相关缺口消失，目标节点的要求与可观察验收通过。

<a id="open-002"></a>
### OPEN-002 我的主页交集聚合入口与清零 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：我的主页展示交集总数与最多 3 个维度的变化红点/数字，超 3 维度可展开更多。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-003"></a>
### OPEN-003 对象页交集卡与 demo dock 移除 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：profile/entity/circle 三类主页不再出现问小趣 demo dock。
- 完成判定：`SIT-002` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-004"></a>
### OPEN-004 首页与频道交集推荐重设计 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：首页交集卡去掉关注按钮，使用真实头像 + 名字 + 维度 chip + 安静共同点 chip。
- 完成判定：`SIT-003` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-005"></a>
### OPEN-005 保鲜冷却与曝光转化漏斗 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：曝光未转化的交集对象在配置窗口（默认 14 天）内不再重复推荐。
- 完成判定：`SIT-004` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-006"></a>
### OPEN-006 v3 可行动交集与商用主轴 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：交集触点统一遵循产品主轴「别人帮你刷内容，我们帮你遇到对的人」；所有可见交集句只读云侧 primaryText/primarySpans/displayBinding，端不拼句，join(spans.text)==primaryText 不变量成立。
- 完成判定：`SIT-005` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-007"></a>
### OPEN-007 旅游 POI / 实体主页经纬度语料回填

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：代码链路已接上 `Location` / GeoJSON / `filters.near`，但 canonical travel 实体坐标回填仍为 0/2899，`coPresentHere` / `nearbyAffinity` 与 near 检索无法在真实语料上成立。
- 完成判定：`quwoquan_data/reference/travel/entities/**` 坐标覆盖达到可商用阈值，且 gamma import receipt 证明 near 检索返回非空。
