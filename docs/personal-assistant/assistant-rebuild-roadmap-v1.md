# 小趣助手脱胎换骨重构路标（Roadmap v1）

## 1. 文档目的

本路标文档用于统一未来多个串行会话的实施方向，避免继续围绕现象做补丁式修复。

使用方式：

1. 每个新会话开始前，先读本文件。
2. 再读 `assistant-rebuild-design-context-v1.md`。
3. 再复制对应里程碑的启动提示词。
4. 每个里程碑完成后，回写本文件中的状态和结论。

---

## 2. 北极星目标

最终要把当前个人助手重构成一个同时满足以下目标的系统：

- 过程可解释：用户看到的是平滑、可信、只追加不回写的过程叙事。
- 答案可展示：最终答案永远是用户可读内容，不再泄漏 JSON、协议字段、trace、内部状态。
- 证据可追溯：关键结论可绑定到引用源，引用能展开、收起、增量更新。
- 默认可用：无模型、弱网、检索失败时仍有最低质量保证，而不是单句失败提示。
- skill 可扩展：skill 不再另起炉灶，而是在默认处理基座上做增量覆盖。
- 状态可治理：槽位、对话状态、追问、部分回答、重规划、权威源策略全部可配置、可扩展。
- 结构可维护：去掉多条并行协议和重复适配层，职责清晰、主链唯一。

---

## 3. 当前已确认问题

以下问题已经通过真实问题联调或代码检查确认：

- 用户态过程总线并行存在多套协议，导致直播内容和完成态内容容易重复、互相覆盖。
- 内部摘要流程会把 `summarize_session` 之类的内部任务串进用户可见过程流。
- `finalText` 仍承载机器 envelope，最终显示和存储层存在 JSON 泄漏风险。
- 流式时真实产生了很多事件，但最终持久化的 `uiProcessTimelineV2` 会被压缩成少量条目，丢失真实历史。
- 默认兜底能力已经开始承担意图、规划、成答职责，但仍嵌在 `llm_provider.dart` 中，职责越界明显。
- 检索失败后会快速落到 fallback，但证据账、快速切源、权威源策略、最小可用答案仍不够系统化。

---

## 4. 不可妥协的架构约束

所有里程碑都必须遵守下面这些约束：

- 用户可见过程只能有一条主总线。
- 叙事正文必须 append-only；只有当前直播行可以 replace。
- 资料列表、引用计数、来源摘要允许增量更新，但不能回改已经说过的话。
- 内部 trace 默认不可见，必须经过可见性过滤后才能进入用户过程流。
- 机器产物和展示产物必须分账。
- 默认处理是基座，skill 是 overlay，不允许 skill 绕过质量底线。
- 实时事实型和复杂规划型问题都必须有最低质量兜底。
- 每个里程碑都必须包含真实问题联调，不只跑单测。

---

## 5. 里程碑总览

| 里程碑 | 名称 | 目标摘要 | 状态 | 依赖 |
|---|---|---|---|---|
| M1 | 核心契约冻结 + 单一过程总线 | 冻结主契约，切断内部串味，统一用户态过程流 | completed | 无 |
| M2 | 输出双账 + 最终收口 + append-only 持久化 | 分离机器/展示产物，解决 JSON 泄漏与历史压缩 | completed | M1 |
| M3 | 默认处理基座化 + 检索 Broker + 证据账 | 建立最小可用基座、快速切源、证据系统 | completed | M2 |
| M4 | 槽位/状态内核 + DomainPolicyBundle + skill overlay | 统一槽位、状态机、skill 扩展模型 | completed | M3 |
| M5 | 答案/叙事统一引擎 + 引用绑定 + legacy 清退 + 总体验收 | 统一最终体验并完成旧链路清退 | completed | M4 |

---

## 6. 里程碑 1：核心契约冻结 + 单一过程总线

### 6.1 目标

先把整个用户态过程链收口成一条主线，让后续重构有稳定基座。

### 6.2 核心交付

- 冻结核心契约：
  - `RunArtifacts`
  - `ProcessJournalEvent`
  - `TraceVisibility`
  - `EvidenceLedgerEntry`
  - `SlotStateSnapshot`
  - `DomainPolicyBundle`
- 将用户态过程统一为：
  - `stage_set`
  - `narrative_commit`
  - `live_cursor`
  - `source_update`
  - `answer_delta`
  - `completed`
- 为以下内部链路增加 `internal` 可见性：
  - `summarize_session`
  - 记忆提炼
  - 内部分域分类
  - 内部补救/修复 trace
- 将旧协议适配为兼容桥，不再作为主数据源。

### 6.3 本里程碑必须解决

- 用户过程里不再出现内部摘要/压缩任务
- 除直播行外，不再有过程历史回写
- 不再依赖多套并行主协议来驱动 UI

### 6.4 验收

- 真实联调中，用户过程不再出现“压缩以上对话历史为简洁摘要”等串味内容
- 非 thinking 的 `processReplace` 归零
- 过程流只保留一条主线，其他协议仅作兼容适配

### 6.5 本次完成结论（2026-03-12）

- 已冻结主契约：`RunArtifacts`、`ProcessJournalEvent`、`TraceVisibility`、`EvidenceLedgerEntry`、`SlotStateSnapshot`、`DomainPolicyBundle`
- 已建立 `ProcessJournalBus`，并让 `CapabilityGateway` / `AgentLoop` / `chat_detail_page` 以 `processJournalV1` 作为用户态主线
- 已将 `summarize_session`、内部补救与内部推理 trace 标记为 `internal` 或 `system`，不再进入用户过程叙事
- 已保留 `userEvent`、`uiProcessTimelineV2`、`explainableFlowEvent`、`processUpdate` 作为兼容桥，但不再是主驱动源
- 已验证 append-only 约束：叙事正文只追加；仅 `live_cursor` 允许替换当前直播行
- 已完成回归：
  - `process_journal_bus_test.dart`
  - `assistant_contract_models_test.dart`
  - `phase_lifecycle_e2e_test.dart`
  - `assistant_run_e2e_test.dart`
  - `chat_detail_page_assistant_ui_regression_test.dart`
  - `process_event_consolidator_test.dart`
  - `full_phase_pipeline_test.dart`
- 已完成一次真实天气联调，日志显示内部 `summarize_session` 仍存在于内部 trace，但不会进入 `processJournalV1`
- 已完成一次复杂规划型真实联调（`深圳三天两晚住宿和行程，预算4000元`），`processJournalV1` 未再串入内部摘要任务
- 剩余风险：
  - 旧兼容桥 `uiPhaseTimelineV1` 在复杂规划型日志里仍可能保留 JSON 片段；虽然主 UI 已优先消费 `processJournalV1`，但这类 legacy 漏出仍需在 M2 一并清退
  - `dart run tool/assistant_e2e_probe.dart` 当前无法直接作为 live probe 入口，需后续改成 Flutter 测试/Flutter runner 方式

---

## 7. 里程碑 2：输出双账 + 最终收口 + append-only 持久化

### 7.1 目标

彻底解决 JSON 泄漏、最终结果二次刷新、历史被压缩的问题。

### 7.2 核心交付

- 分离三类产物：
  - `machineEnvelope`
  - `displayMarkdown`
  - `displayPlainText`
- 让 `CompletedArtifact` 成为展示与存储的最终收口对象。
- UI 和存储不再直接信任 `finalText`。
- `processJournalV1` 成为 append-only 持久化真相源，`uiProcessTimelineV2` 退化为兼容镜像。
- session、memory、摘要统一只读取 `displayPlainText`。

### 7.3 本里程碑必须解决

- 最终显示内容不再出现 `assistant_turn_v4`、`contractVersion`、JSON envelope
- 不再“流式说过一次，结束又刷一遍”
- 最终 timeline 不再从大量流式历史压成极少条 summary

### 7.4 验收

- 真实联调中最终展示无 JSON 泄漏
- 持久化 timeline 条数与流式 commit 数量接近
- 记忆、摘要、session 文本不再被 envelope 污染

### 7.5 本次完成结论（2026-03-12）

- 已将 `RunArtifacts` 明确升级为最终收口对象：统一承载 `machineEnvelope`、`displayMarkdown`、`displayPlainText`、`processJournal`
- 已让 `AssistantRunResponse` 暴露 `machineEnvelopeV1`、`displayMarkdownV1`、`displayPlainTextV1`，下游不再自己猜 `finalText`
- 已在 `agent_loop.dart` 中统一生成展示账，并让 session topic summary、history summary、memory 统一读取 `displayPlainText`
- 已在 `chat_detail_page.dart` 中切换 UI、replay、learning 链路到 display 字段，消息完成态与会话重载不再直接信任 `finalText`
- 已在 `chat_message_bubble.dart` 中增加 `processJournalV1` 恢复能力；历史过程抽屉现在优先从 `processJournalV1/runArtifactsV1.processJournal` 重建，而不是依赖 `uiProcessTimelineV2`
- 已将 HTTP / API / SSE final 包统一切到 `response.toJson()`，远端桥可直接拿到 `structuredResponse/runArtifactsV1`
- 已移除远端 SSE final 非 JSON 时“把原始 payload 当答案”的兜底，改为安全失败并触发本地回退，避免再次把机器账直接展示给用户
- 已完成回归：
  - `assistant_contract_models_test.dart`
  - `full_phase_pipeline_test.dart`
  - `chat_detail_page_assistant_ui_regression_test.dart`
  - `phase_lifecycle_e2e_test.dart`
  - `assistant_run_e2e_test.dart`
- 已完成两类真实问题联调：
  - 简单事实问题：`深圳天气怎么样`
  - 复杂规划问题：`帮我规划深圳三天两晚住宿和行程，预算4000元`
- 本轮联调确认：
  - `displayMarkdown/displayPlainText` 均已落值
  - 最终展示不再泄漏 `contractVersion` / JSON envelope
  - 主过程日志未再串入 `summarize_session` 等内部摘要任务
- 剩余风险：
  - `processJournalV1` 对 `live_cursor/source_update` 仍是“用户态当前快照 + 叙事追加”模型，不是完整原始事件账；若后续要做逐帧回放或严格审计，需要在 M5 再清一次兼容模型
  - `uiPhaseTimelineV1` 仍作为 legacy 兼容桥保留，主 UI 已不再依赖它，但彻底清退应放到 M5

---

## 8. 里程碑 3：默认处理基座化 + 检索 Broker + 证据账

### 8.1 目标

让默认处理成为真正的基座：无 skill、无模型、检索不稳时，也能稳定给出最小可用结果。

### 8.2 核心交付

- 从 `HeuristicLocalLlmProvider` 中迁出 `BaselineKernel`
  - `QueryNormalizer`
  - `ProblemFramer`
  - `RetrievalPlanner`
  - `EvidenceEvaluator`
  - `NarrativeEngine`
  - `AnswerComposer`
- 建立 `RetrievalBroker`
  - provider 快速切源
  - `queryTasks` 维度并行
  - authority/source policy
- 建立 `EvidenceLedger`
  - 权威度
  - 时效性
  - 相关性
  - 槽位贡献
  - claim-to-source 关联基础数据
- 建立默认兜底质量门槛：
  - `F0 Render-safe`
  - `F1 Structure-safe`
  - `F2 Task-safe`
  - `F3 Evidence-safe`

### 8.2.1 当前已落地 bootstrap（进行中）

- 已新增 `BaselineKernel / DefaultProblemFramer / DefaultRetrievalPlanner` 首批骨架，并接回 `HeuristicLocalLlmProvider`
- 已新增 `RetrievalBroker` 接口与 `LegacyToolRetrievalBroker`，`web_search / web_fetch` 已先经 broker 注入链执行
- 已补齐 bootstrap 单测与回归，确保不破坏 M2 的 `processJournalV1` 主链与默认 fallback 行为

### 8.3 本里程碑必须解决

- 无模型/无网时不再只吐一句失败提示
- provider 失败不再依赖模型慢思考是否重试
- 有资料时必须形成最基本证据链
- 复杂规划型问题最差也要输出维度框架或澄清问题

### 8.4 验收

- `深圳天气` 在无模型或检索失败时仍有结构化最小答案
- `深圳住宿/行程` 在证据不足时仍有维度框架或澄清问题
- provider 故障时能自动快速切换，不直接坠落为裸失败

### 8.5 本次完成结论（2026-03-13）

- 已建立 `BaselineKernel`，并把默认处理拆为：
  - `DefaultProblemFramer`
  - `DefaultRetrievalPlanner`
  - `DefaultEvidenceEvaluator`
  - `NarrativeEngine`
  - `AnswerComposer`
- 已建立 `RetrievalBroker` / `LegacyToolRetrievalBroker`，`web_search` / `web_fetch` 通过 broker 注入执行，默认处理不再直连具体工具细节。
- 已建立 `EvidenceLedger` 并写入 `RunArtifacts` 与 `structuredResponse`，后续答案引用、过程来源与权威源排序均可复用同一证据账。
- 已让无模型、检索失败和复杂规划证据不足场景统一走结构化兜底，而不是单句失败提示。
- 已完成回归：
  - `baseline_kernel_bootstrap_test.dart`
  - `retrieval_broker_tool_delegation_test.dart`
  - `llm_provider_heuristic_test.dart`
  - `full_phase_pipeline_test.dart`
- 当前保留项：
  - broker 默认实现仍通过 legacy tool adapter 承接，但上层已只依赖 broker 接口；后续替换底层 provider 不再影响默认处理主链。

---

## 9. 里程碑 4：槽位/状态内核 + DomainPolicyBundle + skill overlay

### 9.1 目标

把默认处理、对话状态、槽位和 skill 扩展统一进一个可治理的中台层。

### 9.2 核心交付

- typed `SlotState`
  - `missing`
  - `inferred`
  - `confirmed`
  - `stale`
  - `conflicted`
- `ConversationStateKernel`
  - ask_user
  - partial_answer
  - replan
  - final_answer_ready
- 将现有：
  - `SkillExecutionShell`
  - `DialogueRoundScript`
  - `fallback_general_search`
  统一收编到 `DomainPolicyBundle`
- 建立 skill overlay 机制：
  - 默认基座提供最低质量和通用能力
  - skill 只做增量覆盖，不另起一套流程

### 9.3 本里程碑必须解决

- skill 不得绕过默认处理质量底线
- 槽位、追问、补查、部分回答、重规划不再 scattered hardcode
- 至少三类域共享同一主流程：
  - `fallback_general_search`
  - `weather`
  - `travel/lodging`

### 9.4 验收

- 追问场景能承接已知槽位，不再上下文重置
- 不同域仅 policy 不同，不再复制一整套执行链
- skill 扩展后仍可回落到默认处理

### 9.5 本次完成结论（2026-03-13）

- 已建立 typed 槽位快照：
  - `SlotStateSnapshot`
  - `SlotValueSnapshot`
  - `missing / inferred / confirmed / stale / conflicted`
- 已建立 `ConversationStateKernel`，将 `ask_user / partial_answer / replan / final_answer_ready` 统一收口为状态机决策。
- 已将 `DialogueRoundScript`、`SkillExecutionShell`、域级检索/证据/对话策略统一汇入 `DomainPolicyBundle`，并在 `AgentLoop` 中支持跨轮续转。
- 已验证默认基座与 skill overlay 共用同一主流程，`weather`、`fallback_general_search`、`travel/lodging` 不再复制多套执行链。
- 已完成回归：
  - `full_phase_pipeline_test.dart`
  - `assistant_contract_models_test.dart`
  - `assistant_run_e2e_test.dart`
- 当前保留项：
  - policy 细化仍可继续演进，但主链已经稳定为“默认处理基座 + policy overlay”的单一路径。

---

## 10. 里程碑 5：答案/叙事统一引擎 + 引用绑定 + legacy 清退 + 总体验收

### 10.1 目标

统一最终体验，并清退补丁时代留下的旧并行协议和重复适配层。

### 10.2 核心交付

- 统一 `AnswerComposer + NarrativeEngine`
- claim-to-evidence 绑定
- inline evidence links / `🔗` 支持
- 资料展开与过程挂载统一渲染
- 清退 legacy：
  - `phaseTimeline` 不再作为主数据源
  - `userPhaseEvent/processUpdate` 不再承担主职责
  - 多套兼容桥缩减为最小 facade

### 10.3 本里程碑必须解决

- 关键结论可挂到对应证据源
- 无证据时也要保持结构、逻辑和可执行性
- 代码结构能清楚解释：
  - 默认处理在哪
  - skill overlay 在哪
  - 证据账在哪
  - 状态机在哪
  - 用户态过程总线在哪

### 10.4 验收

- `深圳天气`：流式平滑、权威源优先、最终无 JSON
- `深圳住宿/行程`：多维拆查、补查理由清楚、过程不回写
- `无模型`：最小可用答案
- `无网/检索失败`：结构化降级，不是单句失败
- legacy 主职责清退完成，主链唯一

### 10.5 本次完成结论（2026-03-13）

- 已将 `AnswerComposer + NarrativeEngine` 统一接入最终展示链，正常成答与默认兜底均通过同一套展示账、过程账和引用账输出。
- 已建立 `AnswerEvidenceBinding`，并同时输出到：
  - `runArtifactsV1.answerEvidenceBindings`
  - `uiAnswer.evidenceBindings`
  关键结论可绑定到具体证据对象，而不再只是弱语义的链接拼接。
- 已支持答案内联来源链接，最终答案里的 `[来源N](url)` 与过程区 `processJournalV1/source_update` 共用同一来源集合。
- 已确认新结果主链只以 `processJournalV1 + runArtifactsV1 + uiAnswer` 驱动；`userEvents / uiProcessTimelineV2 / uiPhaseTimelineV1` 不再作为新结果主数据源，仅保留历史恢复兼容 facade。
- 已确认主 UI 优先消费 `processJournalV1`，过程抽屉、最终答案与来源展开渲染已统一到单一展示体验。
- 已完成总体验收回归：
  - `full_phase_pipeline_test.dart`
  - `phase_lifecycle_e2e_test.dart`
  - `assistant_run_e2e_test.dart`
  - `new_tools_e2e_test.dart`
  - `synthesis_guard_contract_test.dart`
  - `llm_provider_heuristic_test.dart`
  - `retrieval_broker_tool_delegation_test.dart`
  - `process_journal_bus_test.dart`
  - `assistant_contract_models_test.dart`
  - `chat_detail_page_assistant_ui_regression_test.dart`
- 本轮结论：
  - `深圳天气`：已验证流式过程、权威源优先、最终展示无 JSON 泄漏。
  - `深圳住宿/行程`：已验证复杂规划叙事、补查理由与过程 append-only。
  - `无模型`：已验证默认基座能输出最小可用答案。
  - `无网/检索失败`：已验证结构化降级，而不是单句失败。
- 当前保留项：
  - 仍保留少量 legacy parser/restore 入口用于历史消息兼容；它们已不再承担新结果主职责，若未来要彻底删除，需配合历史会话迁移窗口单独执行。

---

## 11. 跨里程碑执行规则

- 严格串行执行，不并行推进多个里程碑。
- 每个会话只做一个里程碑，不提前做下一个。
- 每个里程碑结束必须更新：
  - 本文档的状态
  - 变更影响范围
  - 未解决风险
- 每个里程碑必须跑：
  - 目标回归测试
  - 至少一轮真实问题联调
- 每个里程碑都要给出“本里程碑内不做什么”。

---

## 12. 最终统一验收清单

- 简单事实型问题能平滑流式，不泄漏内部结构。
- 复杂规划型问题能展示为什么拆维度、为什么补查、为什么暂时不能下结论。
- 关键结论有证据时可挂链接，无证据时明确缺口但不崩坏结构。
- 默认处理在无模型/弱网/检索失败时仍能给出结构化最小答案。
- 追问、补查、部分回答、重规划、状态切换都能解释清楚且不串味。
- 最终持久化的过程日志保留 append-only 历史，不再压缩掉真实过程。

---

## 13. 快速恢复上下文的最短路径

新的里程碑会话开始前，按这个顺序恢复上下文：

1. 读本路标文档，确认当前做哪个里程碑。
2. 读 `assistant-rebuild-design-context-v1.md`，理解当前系统和目标架构。
3. 读 `assistant-rebuild-session-prompts-v1.md` 中对应里程碑的启动提示词。
4. 检查该里程碑涉及的关键代码路径。
5. 跑该里程碑要求的真实问题联调与回归测试。

