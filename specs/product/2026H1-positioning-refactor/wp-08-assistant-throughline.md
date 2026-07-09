# WP8 · 小趣贯穿强化（assistant 端云）

> 树归属：`assistant-run-learning`（多 L2）+ `object-homepage-network/intersection-unified-experience`（解释层）
> 影响 Journey：`assistant-omnipresent-private-assistant`、`assistant-context-grounded-answering`
> 验收意图：SIT + GWT；测试证据：T2 / T3

## 1. 背景与现状

- 小趣已有：全局顶栏入口、首页/发现页半屏面板、对象页交集卡「问问小趣」（`AssistantOpenContext` 解释推荐）、评论/群聊 `@小趣`、小趣搜、技能中心（订阅/授权）、主动兴趣推送（`proactive_interest`）、内容总结（「小趣已为你读完」）。
- 最新实现复核（2026-06-12）：assistant 云侧已具备技能目录、技能订阅、主动 AppMessage、`proactive_interest`、群聊 `@小趣`、answer boundary policy 与 RuntimeFailure 处理；端侧已具备 `AssistantRepository`、技能中心、订阅、`AssistantOpenContext`、私助会话页、AppMessage Repository、我的连接收件箱路由。
- WP1 依赖状态更新：`我的足迹` 的 Repository、页面与 route 已基本落地，本包不再把「引导到我的足迹」视为纯阻塞概念；落地时需要复核 route 可用性与文案边界，但不得把足迹作为交集或影响来源。
- 缺口（对照规格 §2.4 小趣职责）：
  - **辅助创作**：缺 creation-suggest 契约/API/Skill manifest、云侧服务、端侧 Repository 与 WP6 能力探测；
  - **提醒新的交集**：`proactive_interest` 未与交集收件箱水位打通，AppMessage 也缺结构化 route/query 跳转承载；
  - **解释推荐**：对象页「问问小趣」目前只具备 CTA 文案映射，调用方仍以打点为主；内容卡/作品交集详情缺「问问小趣」入口。

## 2. 功能规格

### 2.0 统一概念基线（本包必须遵守）

- 小趣解释、提醒与创作辅助必须基于动作基线：`认同（赞）/ 交流（评）/ 传播（转）/ 持续连接（关注人、关注实体、加入圈子）`；内容无长期动作。
- 小趣不得把“收藏 / 关注内容 / 稍后看”解释为任何动作；涉及以后再看、知识保留、后续跟进时，统一引导到 `我的足迹`（自动记录）或更高价值的对象级动作（进入圈子、关注对象、建立连接）。
- 因此本包的提醒文案、解释推荐文案、创作辅助建议，都应优先放大“进入讨论”“加入圈子”“关注对象”等长期连接结果。
- **依赖注记**：「我的足迹」端侧 Repository / 页面 / route 已进入当前实现基线；本包只复核可跳转状态与文案边界。足迹只能承载「以后再看」解释，不产生交集提醒、不进入影响数字、不作为任何 `primaryText` 事实来源。

### 2.1 创作辅助技能（供 WP6 消费）

- assistant 域新增「创作辅助」技能：输入草稿上下文（标题/摘要/正文摘要/已绑圈子/主挂载），输出建议标签（路径制 tagRef）、建议关联对象、可选标题/摘要建议。
- API 契约（与 WP6 共同冻结，最终 path 经 assistant metadata 定稿）：请求 `{draftTitle, draftSummary, bodyDigest, boundCircleIds[], primaryHomepageId}` → 响应 `{suggestedTagRefs[], suggestedHomepages[{id,type,displayName}], suggestedTitle?, suggestedSummary?}`。
- 技能登记进技能目录（`skill_catalog`），受订阅/授权开关管控；建议结果必须可溯源（基于 taxonomy 与对象读模型，不得编造 tagRef/对象 id）。
- 端侧 `AssistantRepository` 必须提供三层方法（Abstract / Mock / Remote），Remote 使用 metadata path/header/decoder；WP6 发布页只通过能力探测决定入口显隐，不直接依赖具体实现。

### 2.2 新交集提醒

> **依赖顺序**：本节依赖 WP1·T2（六类真实数据源）——无真实 fact 交集增量则提醒无数据可消费；gamma T3 验收必须排在 WP1·T2/T3 合入之后。

- `proactive_interest` 消费交集收件箱增量（per-dimension 已读水位之上的新 fact 交集），生成小趣提醒 AppMessage：「你和{对象}有了新的交集：{primaryText}」。
- 点击提醒跳转 `/profile/intersections?dimension=`（我的连接收件箱），完成 §20.1 闭环的「产生交集→建立关系」承接。
- 频控与免打扰策略经 assistant 域既有策略配置，禁止硬编码阈值。
- AppMessage 必须结构化承载目标 route/query：`target.routeId = myIntersections`、`target.query.dimension = <dimension>`（字段名以 notification metadata 最终 codegen 为准）。禁止用非结构化 summary/title 或硬拼 URL 作为唯一跳转依据。
- 触发源只允许 fact 交集；affinity 不触发主动提醒；提醒文案不得出现 `收藏 / 稍后看 / 关注内容`。

### 2.3 内容卡解释推荐入口

- 内容卡交集理由位长按（或理由详情 sheet 内）增加「问问小趣」，携带 `AssistantOpenContext`（reason 结构化上下文），对齐对象页交集卡既有模式；小趣回答必须基于透传上下文（B2），不得脱离 reason 自由发挥。
- 首发入口优先放在交集详情 sheet 或对象页交集卡动作区，不在瀑布流封面上叠加强按钮，避免破坏「内容优先」原则。

## 3. 周边契约

- 创作辅助 API 形状以本简报 §2.1 为冻结契约（与 WP6 双向依赖的唯一接口）；变更需双包确认并更新两份简报。
- `AssistantOpenContext` 扩展若需新字段，经 assistant metadata；消费 WP1 的 reason 结构（只读）。
- 内容卡入口落点在 `intersection_reason_chip.dart` 详情 sheet 层——该文件归 WP2：本包以「入口挂接清单」交接 WP2，或仅改 sheet（`_WorksIntersectionDetailSheet` 归 WP7 文件）时与对应包协调；默认本包只做 assistant 侧能力 + 半屏面板内入口，卡位挂接由集成会话统筹。
- AppMessage 结构化跳转字段若当前 DTO 不支持，必须先改 notification metadata 并 codegen，再改 assistant-service domain model 与 App 解析逻辑；不得在端侧硬编码解析 `summary` 文案。

## 4. 改动范围

- `quwoquan_service/services/assistant-service/internal/application/`（skill_catalog、创作辅助技能、proactive_interest 交集水位消费）
- `contracts/metadata/assistant/**`（技能、API、AppMessage 模板）
- `quwoquan_app/lib/ui/assistant/`（半屏面板/会话内创作辅助呈现）、通知行跳转
- `quwoquan_app/lib/cloud/services/`（assistant repository 扩展，三层）
- 对应测试

## 5. 准出要求

1. T1：创作辅助 API 契约测试（请求/响应形状、tagRef 必须存在于 taxonomy、对象 id 必须可解析）。
2. T2：技能目录登记 + 订阅开关行为测试；提醒频控测试。
3. T3：gamma 环境——发布草稿调用创作辅助返回可用建议；制造新交集后收到小趣提醒并跳转收件箱。
4. `bash quwoquan_ops/gate/gate_repo.sh --scope service` 与 `--scope app` 全绿；`verify-app-assistant-old-stack-retired` 等 assistant 门禁保持绿。
5. 答案边界：解释推荐回答仅基于透传上下文（既有 answer_boundary_policy 测试覆盖新入口）。
6. AppMessage route/query roundtrip 与端侧点击跳转测试通过；未知 target 结构化降级、不 crash。

## 6. 验收标准（GWT 样例）

- Given 我有一篇关于九寨沟的长文草稿，When 调用小趣创作辅助，Then 返回的 suggestedTagRefs 含旅行/九寨沟相关路径制标签、suggestedHomepages 含九寨沟对象，且全部真实存在。
- Given 我与某用户新产生「共同讨论」交集且超过已读水位，Then 收到小趣提醒，点击进入我的连接收件箱对应维度。
- Given 我未订阅创作辅助技能，Then WP6 发布页探测不到该能力，入口不出现。
- Given 内容交集详情中有云侧 reason，When 点击「问问小趣」，Then 打开小趣并携带 reason 上下文；小趣只解释该 reason，不新增未提供事实。
