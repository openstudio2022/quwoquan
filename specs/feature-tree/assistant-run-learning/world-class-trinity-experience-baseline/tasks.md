# world-class-trinity-experience-baseline 任务列表

## 当前交付任务

### 包 1：Unified Runtime Mainline

- [ ] T1: [metadata] 更新 `quwoquan_service/contracts/metadata/assistant/assistant_run/fields.yaml`，补齐过程摘要、来源计数、本会话偏好事实、长期偏好事实字段。
- [ ] T2: [metadata] 更新 `quwoquan_service/contracts/metadata/assistant/assistant_run/service.yaml`，补齐过程区、偏好事实与 fallback 相关 contract test 场景。
- [ ] T3: [codegen] 执行 `make verify && make codegen && make codegen-app`，确认 assistant_run 相关 generated 产物可生成。
- [ ] T4: [测试/Red] 为问题分型、stop policy、remote/local/hybrid 行为一致性补齐最小失败测试骨架（T1/T3）。
- [ ] T5: [业务逻辑] 重构 `AgentLoop` 主线，明确 `Planner -> Skill Shell -> ReactRuntime -> Synthesizer` 边界。
- [ ] T6: [业务逻辑] 清理 runtime 中残余领域硬编码，保留通用 ReAct、守卫、预算与 fallback 机制。
- [ ] T7: [业务逻辑] 对齐 `CapabilityGateway`、`OpenClawBridge` 与本地执行结果的统一能力面和质量门控。
- [ ] T8: [测试/Green] 跑通 `localOnly / remotePreferred / hybrid` 三路径一致性测试并转绿。

### 包 2：Skill DSL 2.0

- [ ] T9: [metadata/规范] 定义 Skill DSL 2.0 最小字段集：`manifest / slot_contract / dialogue_state / tool_binding / response_style / reference_policy / execution_shell / preference_hooks`。
- [ ] T10: [测试/Red] 为 Skill DSL 结构与兼容迁移编写 contract test，确保旧 `SKILL.md` 可逐步升级而不破坏现有加载逻辑。
- [ ] T11: [业务逻辑] 升级 Skill loader / planner 注入逻辑，使 Planner 可消费新的 Skill Shell 结构。
- [ ] T12: [业务逻辑] 完成天气 Skill 的 DSL 2.0 首个试点，实现短预算、强收敛、实时证据优先。
- [ ] T13: [业务逻辑] 完成 `shopping_decision` Skill 试点，实现对比型结构输出与明确推荐。
- [ ] T14: [业务逻辑] 完成 `social_companion_chat` Skill 试点，实现少结构、弱过程、弱工具感闲聊主线。
- [ ] T15: [业务逻辑] 完成 `fallback_general_search` Skill 试点，实现高质量通用兜底。
- [ ] T16: [测试/Green] 跑通 4 个试点 Skill 的 contract / integration 回归测试。

### 包 3：Markdown-first Rendering

- [ ] T17: [测试/Red] 为主答复 Markdown-first、过程区折叠、一行摘要 + 可展开来源计数、少量 emoji 约束编写 UI regression tests。
- [ ] T18: [业务逻辑] 在结构化结果中引入 `processSummary` 与 `processReferenceCount` 统一字段，禁止 UI 自由拼接过程语义。
- [ ] T19: [业务逻辑] 重构 `ChatDetailPage` / 相关消息组件，使主答复优先、过程区默认折叠且围绕用户目标进展表达。
- [ ] T20: [业务逻辑] 将天气等高频垂类主答复统一为精排 Markdown，不新增专属卡片组件。
- [ ] T21: [业务逻辑] 统一 Markdown 降级路径，确保结构解析失败时安全回退到普通 Markdown。
- [ ] T22: [测试/Green] 转绿 UI 渲染、过程区、引用展开与 Markdown 降级相关测试。

### 包 4：Session + Long-term Preference Facts

- [ ] T23: [metadata] 在 `assistant_run` 及相关交互事件持久化结构中挂载本会话偏好事实与长期偏好事实引用。
- [ ] T24: [测试/Red] 为偏好事实 schema、本会话即时生效和长期事实可见可撤销设计单测与 VM 测试。
- [ ] T25: [业务逻辑] 统一“重新生成 / 点赞点踩 / 过程展开 / 引用展开 / 纠正文本”的事实采集结构。
- [ ] T26: [业务逻辑] 让本会话偏好即时注入 Planner / Synthesizer / Skill Shell，影响同会话后续回答。
- [ ] T27: [业务逻辑] 实现长期偏好事实读取与设置页展示、撤销入口；当前仅做事实记录，不做自动强学习。
- [ ] T28: [测试/Green] 转绿偏好事实采集、注入、设置展示与撤销测试。

### 包 5：Fallback General Skill High-quality Baseline

- [ ] T29: [测试/Red] 为结构化输出异常、低质量搜索、工具失败、远端不可用等 fallback 场景补齐 contract tests。
- [ ] T30: [业务逻辑] 明确 fallback general skill 的触发条件、Markdown 骨架、边界声明与下一步建议格式。
- [ ] T31: [业务逻辑] 将低质量搜索 stop policy 与 fallback general skill 接通，避免简单问题长时间不收敛。
- [ ] T32: [业务逻辑] 将远端结果不合格、本地工具失败、模型结构异常统一导向高质量兜底路径。
- [ ] T33: [测试/Green] 转绿 fallback 相关 contract / integration / weak-network 回归测试。

### 全链质量与发布收口

- [ ] T34: [测试] 建立 `A1~A13 ↔ T1~T4` 证据映射回填，补齐缺失的测试入口与函数引用。
- [ ] T35: [测试] 执行 `python3 quwoquan_app/scripts/runtime/verify_dart_semantic.py`，确保助理 UI 无新增硬编码视觉字面量。
- [ ] T36: [测试] 执行 `make gate` 与 `make gate-full` 所需最小闭环，确认 metadata、codegen、契约、UI 回归可复跑。
- [ ] T37: [发布] 配置灰度开关：`skill_shell_v2_enabled`、`markdown_first_rendering_enabled`、`session_preference_facts_enabled`、`fallback_general_skill_enabled`、`problem_class_routing_enabled`。
- [ ] T38: [发布] 按 5% / 25% / 50% / 100% 规划天气试点到统一主线的放量步骤，并定义回滚阈值。

### 统一主线归一任务

- [ ] T39: [规格/实现] 在 `spec.md / design.md / acceptance.yaml` 中冻结 `IntentGraph`、`skillRuns[]`、`AggregationState`、`UserEvent`、`uiProcessTimelineV2` 的正式定义与边界。
- [ ] T40: [测试/Red] 为 `IntentGraph` 建立契约测试，覆盖单 skill、双 skill、需澄清三种输入。
- [ ] T41: [metadata] 扩展 `assistant_run/fields.yaml`，补齐 `problemShape`、`primarySkill`、`secondarySkills`、`skillRuns`、`aggregationState`、`uiProcessTimelineV2` 字段。
- [ ] T42: [业务逻辑] 重构入口导引，移除 `ChatDetailPage` 对 `domainId` 的预分类控制权，统一由 engine 产出 `IntentGraph`。
- [ ] T43: [业务逻辑] 在 `AgentLoop` 中落地 `skillRuns[]` orchestrator，使单 skill / 多 skill 共用正式编排主线。
- [ ] T44: [业务逻辑] 为每个 `skillRun` 注入独立 `SkillExecutionShell` 与 `slotState`，禁止父任务预算泄漏到子任务。
- [ ] T45: [测试/Green] 转绿多 skill 问题回归，至少覆盖“天气 + 旅游”与“单天气”两条主线。
- [ ] T46: [业务逻辑] 引入 `AggregationState`，统一处理“全部可答 / 部分可答 / 继续扩展 / 请求澄清”四类出口。
- [ ] T47: [测试/Red] 为 `AggregationState` 建立契约测试，覆盖 `allSkillsReady / needExpansion / canGivePartialAnswer / clarificationNeeded`。
- [ ] T48: [业务逻辑] 重构 synthesizer，把多 skill fusion 升级为正式聚合出口，而不是 `subagentRuns.length > 1` 的补丁分支。
- [ ] T49: [协议] 定义 `UserEvent` 契约，最少支持 `process_replace / process_append / process_commit / answer_delta` 与 `root / skill / aggregation` 作用域。
- [ ] T50: [业务逻辑] 在 `CapabilityGateway` 中引入 `UserEventTranslator`，统一翻译本地 trace 与远端 SSE。
- [ ] T51: [业务逻辑] 扩展 `OpenClawBridge`，兼容新的 `user_event/*` SSE 事件与回放语义。
- [ ] T52: [业务逻辑] 将 `ChatDetailPage` 改为 reducer 驱动，统一消费 `UserEvent` 与完成态消息载荷。
- [ ] T53: [业务逻辑] 持久化消息级 `uiProcessTimelineV2`，修复过程抽屉在完成态与记录重载态消失的问题。
- [ ] T54: [测试/Red] 建立 UI regression，覆盖流式过程先起、答案后起、完成态保留、记录重载恢复。
- [ ] T55: [业务逻辑] 收紧 UI 展示白名单，禁止 `query`、`provider`、`freshnessHoursMax`、`assistant_turn_v4`、tool args、XML tool_call 泄漏到用户。
- [ ] T56: [测试/Green] 转绿“结构脏输出 / XML tool_call / contractVersion 泄漏 / 内部关键字泄漏”回归测试。
- [ ] T57: [发布] 为统一主线增加灰度开关：`intent_graph_enabled`、`multi_skill_orchestrator_enabled`、`aggregation_state_enabled`、`user_event_stream_enabled`、`ui_process_timeline_v2_enabled`。
- [ ] T58: [发布] 定义统一主线的观测与回滚阈值，至少覆盖 `drawer_persist_success_rate`、`internal_leak_rate`、`expansion_overrun_rate`、`answer_ready_rate`。

## 搁置任务（不在本次交付范围，但已识别，有重启条件）

- [ ] 第三方 Skill 商店化、审核流与商业生态（重启条件：本地主线和内建 Skill DSL 2.0 稳定上线后）。
- [ ] 独立云侧 Agent 服务进程与云主端备形态（重启条件：当前本地 + OpenClaw 混合主线稳定，且需要多端统一与集中运维时）。
- [ ] 全端统一渲染与桌面端同构体验（重启条件：移动端 Markdown-first 交互稳定且已有桌面端交付需求时）。

## 未来演进任务

- [ ] 将 Skill DSL 2.0 升级为更强的结构化 schema 与自动验证器（与 design.md“未来演进”对应）。
- [ ] 基于事实积累升级长期偏好标签优化和学习能力，但保持设置页可见可撤销原则。
- [ ] 引入更强的商用质量与成本看板，覆盖 `decision_parse_success`、`render_fallback_rate`、`search_overrun_rate`、`remote_to_local_failover_rate` 等指标。
- [ ] 将 fallback general skill 扩展为跨域融合兜底，支持多域低信心场景下的统一高质量成答。
