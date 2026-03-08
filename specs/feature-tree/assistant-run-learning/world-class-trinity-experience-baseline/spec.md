# L2 特性：world-class-trinity-experience-baseline

## 功能定位

本特性升级为“小趣私人助理统一主线升级”的 PRD 基线，不再以单点垂类优化或单个 UI 补丁为目标，而是以**统一 Agent 主线 + Skill 中心化 + Markdown-first 输出 + 可解释折叠过程 + 偏好事实回注**为核心，建立一条可持续扩展、可灰度、可回退、可对齐业界一流体验的助理运行架构。

一句话目标：

**让小趣对不同问题自动适配最佳处理链路，在简单问题上足够敏捷，在实时问题上足够可信，在任务问题上足够可执行，在复杂推理上足够有条理，并在模型或搜索质量不佳时仍保持稳定、高水准的成答体验。**

## 用户与核心问题

### 目标用户

- 在趣我圈内把“小趣”当成全站私人助理入口的移动端用户。
- 既会问轻问题（天气、解释、随口一问），也会提复杂问题（对比决策、任务执行、内容理解、跨场景咨询）的高频用户。

### 当前核心问题

1. **主线不统一**：`AgentLoop`、`ReactRuntime`、`Tool`、`Skill`、UI 过程区、学习反馈各自有能力，但没有形成稳定统一的端到端主线。
2. **问题分型不稳定**：简单问答、实时问答、任务执行、复杂推理等问题没有被强约束地分流，导致轻问题也可能进入重型搜索和反思链路。
3. **过程表达错位**：当前过程区更像内部 trace 的用户化翻译，而非围绕用户目标的阶段性进展说明。
4. **垂类能力不够中心化**：垂类差异更多散落在 prompt、runtime 和局部逻辑里，而不是由 Skill 统一承载状态机、工具预算、Markdown 风格和收敛策略。
5. **学习闭环未真正回注**：重生成、反馈、引用展开等行为已被记录，但还没有稳定形成“本会话即时生效 + 长期偏好可见可撤销”的主链体验。
6. **鲁棒性不足**：当模型输出质量不佳、搜索结果不充分、远端不可用或工具链失灵时，系统虽有降级能力，但仍缺少一套面向用户的高质量 fallback 体验基线。

## 业界对标输入

### 借鉴对象

- **OpenClaw 类实现**：统一 `run / runStream / skills / invoke` 能力面，远端优先，具备流式事件和渠道互操作能力。
- **主流 Agent Runtime 实践**：模型主导规划，工具元数据驱动，执行层有预算、循环检测、权限守卫和结果截断。
- **一流对话助手体验**：主答复优先、过程可解释但不打扰、简单问题快收敛、复杂问题结构化展开、失败时仍给用户高质量答复而不是纯错误。

### 明确借鉴点

- 统一能力面，而不是本地/远端/渠道各说一套协议。
- 模型主导的 Planner，而不是继续堆垂类硬编码路由。
- Tool Fabric 和安全守卫在模型之外统一治理。
- 输出始终面向用户，主答复优先、过程区折叠。
- Skill 作为领域真相源，承载风格、状态、预算、约束。

### 明确不借鉴点

- 不向用户暴露原始思维链、原始工具 JSON 或系统内部控制语句。
- 不把所有问题都做成重卡片或操作面板，主答复仍以 Markdown 为中心。
- 不为了追求“会思考”而牺牲简单问题的收敛速度。
- 不把兜底能力做成低质模板回复，fallback 也必须是高水准通用能力。

### 适用边界

- 本期优先覆盖移动端小趣主会话与主要入口链路。
- 本期可兼容现有本地运行时和 OpenClaw 远端桥接，不要求新建独立服务进程。
- 本期不做第三方 Skill 商店化运营，不做全端统一 UI 方案。

## 本期 5 个交付包

### 包 1：`Unified Runtime Mainline`

建立统一问题处理主线，使 `AgentLoop + Planner + ReactRuntime + Tool Fabric + CapabilityGateway + UI` 成为一条清晰、稳定、可切换、可观测的主链。

本包目标：

- 明确入口控制面，新增 `IntentGraph` 作为首轮导引结果，至少包含：
  - `problemShape`（`single_skill | multi_skill`）
  - `primarySkill`
  - `secondarySkills`
  - `userGoal`
  - `globalConstraints`
- 明确正式编排面，统一以 `skillRuns[]` 执行单 skill 与多 skill 问题：
  - 单 skill：退化为 1 个 `skillRun`
  - 多 skill：由 `primary + secondary` 组成一组独立 `skillRun`
- 明确聚合面，新增 `AggregationState` 统一判断：
  - `allSkillsReady`
  - `blockingSkills`
  - `canGivePartialAnswer`
  - `needExpansion`
  - `expansionPlan`
  - `finalAnswerReady`
- 明确全局主线职责边界：
  - `AgentLoop`：上下文装配、偏好注入、记忆召回、合成就绪判断、学习事实持久化。
  - `Intent Router`：只做问题理解、问题分型、主副 Skill 拆分与全局约束识别。
  - `Planner`：在已确定的 Skill 范围内做 mode、stop policy、slot fill、query normalization 与执行规划。
  - `ReactRuntime`：只做通用 ReAct 循环，不写垂类 if-else。
  - `Tool Fabric`：统一工具元数据、参数 schema、权限、预算、结果截断、循环检测。
  - `CapabilityGateway`：统一 `localOnly / remotePreferred / hybrid`，并对齐 `run / runStream / skills / invoke` 能力面。
  - `UserEventTranslator`：把内部 trace、tool 结果、聚合状态翻译成用户可解释的事件流。
- 支持问题分型策略，但不在引擎层硬编码某个垂类，差异化通过 Skill Shell 注入。
- 统一本地和远端的结果质量门控，远端不满足商用品质时稳定回退。

### 包 2：`Skill DSL 2.0`

把 Skill 从“轻量 manifest + policy 文本”升级为真正的领域真相源，让垂类体验的差异主要由 Skill 定义，而不是散落在 runtime 与 prompt 的硬编码。

本包目标：

- 每个 Skill 至少具备以下 8 类定义：
  - `manifest`
  - `slot_contract`
  - `dialogue_state`
  - `tool_binding`
  - `response_style`
  - `reference_policy`
  - `execution_shell`
  - `preference_hooks`
- Skill 驱动“不同问题思维链不同”的体验差异：
  - 天气：短预算、强收敛、实时证据优先。
  - 购物对比：允许更多证据整合，必须明确推荐。
  - 闲聊陪伴：少结构、弱过程、弱工具感。
  - 通用兜底：高质量通用 Markdown 成答，不低配。
- 新增领域能力时，优先通过 Skill 扩展而不是改引擎硬编码。

### 包 3：`Markdown-first Rendering`

统一主答复呈现策略：以精排 Markdown 为唯一主输出，过程区默认折叠且只显示最必要的解释信息。

本包目标：

- 主答复统一走高质量 Markdown：
  - 允许标题、强调、引用、表格、少量 emoji、来源引用等结构。
  - 不要求天气等高频场景做专属卡片，重点是 Skill 定义 Markdown 骨架。
- 过程区统一为：
  - `1 行摘要`
  - `1 个可展开的来源计数`
- 过程区正式升级为“用户事件驱动的流式演绎”，只消费：
  - 根层 `root`：入口理解、任务拆分、整体进度
  - Skill 层 `skill`：每个 Skill 的独立推进
  - 聚合层 `aggregation`：是否可答、是否扩展、汇总中
- 流式协议最少覆盖：
  - `process_replace`
  - `process_append`
  - `process_commit`
  - `answer_delta`
- 完成态必须把过程树持久化为 `uiProcessTimelineV2`，保证抽屉在完成后、重载后、切会话后仍可恢复。
- 过程区文案围绕“用户目标进展”，不围绕内部阶段名。
- emoji 全局默认“少量点缀”，同时允许 Skill 在自己的 `response_style` 中增量扩展。
- 结构块或 Markdown 解析失败时，必须安全降级到普通 Markdown，不中断对话。

### 包 4：`Session + Long-term Preference Facts`

建立“本会话即时生效、长期偏好可见可撤销”的偏好事实体系，当前阶段先记录事实并透明管理，不急于做过强的自动学习。

本包目标：

- 本会话偏好优先级最高：
  - 由重生成选项、点赞点踩、过程区展开、引用展开、纠正文本等事实触发。
  - 对本会话后续回答立即生效。
- 长期偏好当前只做“事实记录 + 设置页可见 + 用户可撤销”。
- 偏好标签至少覆盖以下维度：
  - 任务类型偏好
  - 信息密度与结构偏好
  - 表达风格偏好
  - 过程透明度偏好
  - 收敛容忍度偏好
  - 按 Skill/Domain 的局部偏好
- 当前阶段只沉淀事实和标签，不要求自动优化到最终学习策略，但必须保证后续可回注到 Planner 与 Skill Shell。

### 包 5：`Fallback General Skill High-quality Baseline`

建设高水准通用兜底能力，使系统在模型质量、搜索质量、工具可用性不佳时，仍能给出可信、克制、结构合理的答复。

本包目标：

- 定义统一 fallback general skill：
  - 通用解释、有限证据整合、边界声明、建议下一步。
- 遇到以下情况时，系统仍能产出高质量答复：
  - 模型输出结构不稳定
  - 搜索结果质量低或不一致
  - 工具调用失败或预算耗尽
  - 远端不可用、仅剩本地路径
- fallback 不得退化成“机械报错”或“模板拒答”，而要保持主答复质量、可信边界和用户引导。

## 问题分型主线

本特性要求系统对不同问题自动适配不同处理链路，但统一由 Planner + Skill Shell 主导，不在 runtime 中硬编码垂类分支。

### 类型 1：简单问答型

示例：百科、解释、翻译、轻咨询、闲聊。

目标：

- 优先快速收敛。
- 默认少工具或零工具。
- 过程区弱化。

策略：

- 优先直接答复。
- 只有在 Skill 明确要求或用户显式追问时才补证据。
- 不允许无意义扩搜和反思放大。

### 类型 2：实时信息型

示例：天气、AQI、路况、班次、汇率。

目标：

- 可信优先，但必须有明确预算。
- 优先解决槽位，再做实时证据获取。
- 快速形成“当前结论 + 更新时间 + 是否还能继续补充”的结果。

策略：

- 由 Skill 定义关键槽位和 stop policy。
- 主检索次数可控，避免“无限扩大搜索范围”。
- 若证据不足，优先边界声明而非无限循环。

### 类型 3：任务执行型

示例：提醒、日程、导航、设备动作、跨应用操作。

目标：

- 明确动作、确认边界、给回执。
- 用户看见的是任务状态，不是系统搜索过程。

策略：

- 先补槽、再确认、再执行、再返回结果。
- 权限和不可逆操作需统一经 ToolExecutionGuard 或确认流。

### 类型 4：复杂推理型

示例：购物决策、职业规划、政策解读、多因素比较。

目标：

- 结构化地展开 reasoning，而不是乱搜。
- 先搭问题框架，再有限检索，再汇总结论。

策略：

- 允许更高预算，但必须受 Skill Shell 和 stop policy 约束。
- 优先输出“结论 / 依据 / 取舍 / 下一步”，而不是长流水账。
- 若问题是复合问题（如天气 + 旅游、政策 + 决策），应优先拆为多个 `skillRun` 后再聚合，而不是在一个 planner 回合内混合处理全部领域事实。

### 类型 5：通用兜底型

示例：问题意图不清、多域交叉、当前 Skill 信心不足、搜索和模型均不理想。

目标：

- 不失态、不暴露内部混乱。
- 在边界清晰的前提下给出高水准通用答复。

策略：

- 统一落到 fallback general skill。
- 允许提示不确定性，但仍要尽量有帮助。

## 核心产品体验要求

### 1) 主答复优先

- 用户首先看到的是主答复 Markdown，而不是过程区。
- 过程区永远是辅助层，不得抢占主阅读流。

### 2) 过程可解释但折叠

- 默认仅展示：
  - 一行摘要
  - 一项可展开的来源计数
- 过程摘要必须用用户语言表达“已经为你做了什么”，而不是展示内部阶段枚举。
- 过程演绎必须是流式推进，而不是一次性落盘：
  - 先演绎入口理解
  - 再演绎 skill 级推进
  - 最后演绎 aggregation 与成答组织
- 过程区严禁暴露 `query`、`queryVariants`、`freshnessHoursMax`、`provider`、`contractVersion`、`assistant_turn_v4`、tool args 等内部字段。

### 3) Markdown-first

- 主答复统一为高质量 Markdown。
- 少量 emoji 可以增强亲和力，但不得喧宾夺主。
- 不同 Skill 可定义不同 Markdown 编排骨架，但要共享同一渲染能力。

### 4) 本会话偏好即时生效

- 用户选择“更简洁 / 更详细 / 更口语化 / 深度思考”后，后续同会话回答应立即吸收。
- 该偏好必须可被用户理解、可在设置中查看与撤销。

## 鲁棒性与非功能目标

### 体验目标

- 简单问答：首个有用响应应明显快于复杂问题，不得默认走重型检索链。
- 实时问题：应在有限预算内形成可信答复，必要时明确说明更新时间和证据边界。
- 复杂推理：即使需要更多时间，也应尽快给出结构骨架，而不是长时间无反馈。

### 弱网与远端异常

- `remotePreferred` 下远端结果不合格时，必须稳定切回本地，不让用户看到双路叠加或中断。
- 远端不可用、工具失败、搜索无结果时，必须有高质量降级答复。

### 模型与搜索质量不佳

- 当模型结构化输出不稳时，应安全解析和降级，不能让 UI 崩溃或显示原始内部字符串。
- 当搜索质量低时，应优先受 stop policy 和 fallback 控制，而不是持续无上限扩搜。
- 对低质量结果要有“足够即可成答”的收敛策略，避免简单问题不收敛。

### 可扩展性

- 新增 Skill 不应要求修改核心路由硬编码。
- 新增 Tool 不应要求修改多处 prompt 与运行时判断，应优先通过 metadata 注册接入。

## 范围（本期必须覆盖）

- **端侧运行时**：`AgentLoop`、`ReactRuntime`、`LlmProvider`、`CapabilityGateway`、`OpenClawBridge`。
- **Skill 层**：Skill DSL 2.0 基线、试点 Skill、通用 fallback skill。
- **协议层**：`assistant_run` metadata（fields/errors）与 run/stream 响应契约。
- **编排层**：`IntentGraph`、`skillRuns[]`、`AggregationState`。
- **事件层**：`UserEvent`、`uiProcessTimelineV2`、流式过程演绎协议。
- **渲染层**：主答复 Markdown、折叠过程区、偏好相关交互。
- **偏好层**：本会话偏好、长期偏好事实记录、设置页可见可撤销入口。
- **垂类试点**：天气、购物决策、闲聊陪伴、通用兜底四类代表场景。

## 范围（本期不做）

- 新建服务进程与全新领域服务拆分。
- 第三方 Skill 市场化、审核流与商业生态。
- 全端统一渲染与桌面端同构体验。
- 高级自动学习策略调优与标签自动优化，仅保留事实记录和可回注能力。

## 核心契约要求

### 1) 回合输出契约

- 运行时必须支持 `assistant_turn_v2`（或等价版本）：
  - machine channel: JSON 决策（nextAction/toolPlan/slotState/askUser/processSummary/preferenceFacts）
  - user channel: Markdown 展示（summary/evidence/action/follow-up）

### 2) 工具观测契约

- 工具返回必须可结构化解析（ok/errorCode/errorClass/retryable/slotDelta/data）。
- 禁止以用户文案字符串作为关键业务判断条件。

### 3) Skill 契约

- Skill 必须成为领域真相源，至少定义目标、槽位、状态、工具绑定、Markdown 风格、引用策略、执行外壳与偏好挂钩。
- 不允许同一领域能力在 runtime 与 Skill 中形成第二真相源。

### 4) 偏好契约

- 本会话偏好与长期偏好事实必须结构化记录，可被设置页读取与撤销。
- 长期偏好当前不要求自动强学习，但必须具备后续回注 Planner 与 Skill 的兼容字段。

### 5) i18n 与错误边界

- 补槽追问、权限说明、失败恢复必须支持 `l10n_key + args` 或可迁移到该形式。
- fallback 回答中允许保留自然语言，但不得把内部错误直接暴露给用户。

## 适用场景与约束

### 适用场景

- 小趣主会话页
- 由发现、内容详情、圈子、聊天等入口唤起的小趣辅助链路
- 远端优先、本地回退的混合执行模式

### 约束

- 执行顺序强制：`metadata -> verify -> codegen -> logic -> tests`。
- `DO NOT EDIT` 生成文件禁止手改。
- 任何 Markdown 结构解析失败必须降级到普通 Markdown。
- 隐私能力调用（设备、Intent、相册等）必须通过策略网关和权限语义控制。
- 不以“去硬编码”为名放弃必要的预算、权限、循环和结果质量守卫。

## 与父/子节点关系

- 父节点：`assistant-run-learning`
- 强关联：
  - `run-stream-policy`
  - `run-sync-contract/assistant-run-io-contract`
  - `runtime-assistant`
  - `runtime-skill`
  - `runtime-client-foundation/error-permission-display-semantics`

## 交付结果定义

当以下条件全部满足，视为本特性完成：

1. 5 个交付包均具备可执行规格与清晰边界。
2. 系统能对至少 5 类问题（简单问答、实时信息、任务执行、复杂推理、通用兜底）稳定分流和成答。
3. 天气试点完成“模型主导 + Skill 驱动 + Markdown-first + 折叠过程 + 高质量降级”的闭环。
4. `run / runStream / skills / invoke` 能力面与本地/远端切换逻辑保持统一。
5. 本会话偏好可即时生效，长期偏好事实可见、可撤销。
6. 模型质量、搜索质量或远端可用性不佳时，系统仍能输出可接受的高质量答复。
