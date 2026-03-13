# 小趣助手脱胎换骨重构设计上下文（Design Context v1）

## 1. 文档目的

本设计上下文文档用于给后续每个里程碑会话快速恢复任务相关背景、当前结构诊断、目标架构与关键约束。

如果你是新会话：

1. 先读 `assistant-rebuild-roadmap-v1.md`
2. 再读本文
3. 再读 `assistant-rebuild-session-prompts-v1.md` 中对应里程碑提示词

---

## 2. 当前系统的关键诊断

### 2.1 当前用户态主链并不唯一

当前用户态输出同时存在多条总线：

- `userEvent`
- `phaseTimeline`
- `chunk / answerDelta`
- `explainableFlowEvent`

这会导致：

- 流式中说过一遍，结束又刷一遍
- 一部分状态在直播时是 append，完成后又被 summary 覆盖
- 不同消费路径对“同一轮过程”的理解不一致

当前关键代码热点：

- `quwoquan_app/lib/personal_assistant/app/capability_gateway.dart`
- `quwoquan_app/lib/ui/chat/pages/chat_detail_page.dart`

### 2.2 内部 trace 会串进用户过程流

当前内部摘要流程使用了主链 `onTraceEvent`，导致诸如 `summarize_session` 之类的内部任务有机会被翻译成用户态过程。

当前关键代码热点：

- `quwoquan_app/lib/personal_assistant/engine/agent_loop.dart`

### 2.3 `finalText` 仍然既承担机器账，又承担展示账

这意味着：

- envelope 有机会污染最终展示
- storage/memory/session summary 也可能被 envelope 污染
- UI 仍然需要靠过滤器来防止 JSON 泄漏，而不是从结构上避免

当前关键代码热点：

- `quwoquan_app/lib/personal_assistant/engine/agent_loop.dart`
- `quwoquan_app/lib/personal_assistant/engine/llm_response_parser.dart`
- `quwoquan_app/lib/personal_assistant/protocol/assistant_content_filters.dart`

### 2.4 最终 timeline 仍按 node 合并，真实历史会被压扁

真实联调里，流式阶段已经产生了很多用户态事件，但最终存储的 `uiProcessTimelineV2` 仍会被压缩为少量条目。

这意味着：

- “用户看到的实时历史” 和 “最终持久化历史” 不是同一份事实
- 后续重开对话、刷新页面、重建消息时，会出现“前面说过的话不见了”

当前关键代码热点：

- `quwoquan_app/lib/ui/chat/pages/chat_detail_page.dart`
- `quwoquan_app/lib/personal_assistant/engine/agent_loop.dart`

### 2.5 默认兜底逻辑已经越层

当前 `HeuristicLocalLlmProvider` 不再只是 provider 兜底，而是已经开始承担：

- 基础意图判断
- 查询拆分
- 工具规划
- 最小成答

这说明“默认处理基座”需求是真实存在的，但它不应该继续留在 `llm_provider.dart` 内。

当前关键代码热点：

- `quwoquan_app/lib/personal_assistant/engine/llm_provider.dart`

### 2.6 检索仍偏工具视角，而不是证据系统

虽然已经开始支持：

- `queryTasks`
- `authorityDomains`
- `freshnessHoursMax`
- provider fallback

但整体仍未升格为：

- `RetrievalBroker`
- `EvidenceLedger`
- `AuthoritySourcePolicy`

当前关键代码热点：

- `quwoquan_app/lib/personal_assistant/tools/websearch_tool.dart`

---

## 3. 目标架构总图

目标系统建议收敛为下面这条主链：

```text
User Query
  -> Baseline Kernel
  -> Domain Policy Overlay
  -> Retrieval Broker
  -> Evidence Ledger
  -> Conversation State Kernel
  -> Answer Composer / Narrative Engine
  -> Process Journal
  -> UI Adapters
```

---

## 4. 目标核心构件

### 4.1 RunArtifacts

统一定义“一轮运行最终产出的所有内容”。

建议包含：

- `machineEnvelope`
- `displayMarkdown`
- `displayPlainText`
- `processJournal`
- `liveCursor`
- `evidenceLedger`
- `slotState`
- `answerDecision`
- `diagnostics`

### 4.2 ProcessJournal

用户态过程的唯一事实源。

建议事件类型：

- `stage_set`
- `narrative_commit`
- `live_cursor`
- `source_update`
- `answer_delta`
- `completed`

核心约束：

- `narrative_commit` append-only
- `live_cursor` replace-only
- `source_update` 可增量更新引用和来源摘要
- 内部 trace 默认不可见

### 4.3 EvidenceLedger

统一证据账，而不是把引用散在工具结果、answer payload 和 UI summary 中。

建议字段：

- `evidenceId`
- `domainId`
- `dimension`
- `queryTaskId`
- `title`
- `url`
- `sourceHost`
- `sourceTier`
- `freshnessHours`
- `authorityScore`
- `relevanceScore`
- `slotContributions`
- `snippet`
- `retrievedAt`

### 4.4 BaselineKernel

默认处理基座，不依赖 skill 也能完成最基本闭环。

建议拆分组件：

- `QueryNormalizer`
- `ProblemFramer`
- `RetrievalPlanner`
- `EvidenceEvaluator`
- `NarrativeEngine`
- `AnswerComposer`

### 4.5 ConversationStateKernel

统一管理：

- 槽位状态
- 追问
- 部分回答
- 重规划
- 最终可答判断

### 4.6 DomainPolicyBundle

skill 的真正扩展边界。

建议包含：

- `executionPolicy`
- `slotSchema`
- `dialoguePolicy`
- `authorityPolicy`
- `retrievalPolicy`
- `answerPolicy`
- `narrativePolicy`

---

## 5. 目标架构中的层级职责

### 5.1 Orchestration Layer

负责：

- 组织一轮任务执行
- 汇总产物
- 驱动阶段推进
- 统一结束收口

不负责：

- 写具体检索规则
- 写具体 narrative 文案模板
- 直接构造 UI timeline

### 5.2 Model IO Layer

负责：

- 模型请求
- SSE 流
- usage ledger
- machine envelope 原始接收

不负责：

- 默认兜底业务逻辑
- 用户态过程组织
- 最终展示文本收口

### 5.3 Retrieval & Evidence Layer

负责：

- provider 选择与快速切换
- query task 执行与合并
- 证据打分与去重
- 权威源与时效控制

不负责：

- 决定最终回答结构
- 决定用户叙事口径

### 5.4 State & Slot Layer

负责：

- 槽位状态维护
- 状态切换
- ask_user / partial_answer / replan 决策
- 域策略扩展

不负责：

- 直接调用 UI
- 直接拼接最终 Markdown

### 5.5 Narrative & Answer Layer

负责：

- 用户态过程叙事
- 关键结论组织
- claim-to-evidence 绑定
- 最终 `displayMarkdown` 输出

不负责：

- 直接读原始网络响应
- 绕开证据账自行拼引用

### 5.6 UI Adapter Layer

负责：

- 消费 `ProcessJournal`
- 渲染直播行、已提交叙事、来源列表
- 展示最终答案

不负责：

- 决定过程合并策略
- 解析内部 trace

---

## 6. 现有代码到目标架构的迁移映射

| 当前热点 | 现职责 | 问题 | 目标归属 |
|---|---|---|---|
| `agent_loop.dart` | 调度、收口、timeline 组装、memory、summary | 过胖 | `orchestrator/` + `artifact_builder/` + `session_summary_service/` |
| `llm_provider.dart` | 模型 IO + fallback 业务逻辑 | 越层 | `model_io/` + `baseline_kernel/` |
| `capability_gateway.dart` | 路由、流式桥接、协议翻译 | 并行协议过多 | `stream_bridge/` + `journal_adapter/` + `trace_visibility_filter/` |
| `chat_detail_page.dart` | timeline merge + UI reducer + 渲染辅助 | 逻辑耦合 | `process_journal_reducer/` + UI consumer |
| `websearch_tool.dart` | provider、policy、fallback、summary、refs | 职责过重 | `retrieval_broker/` + tool executor + `evidence_ledger/` |
| `dialogue_state_runtime.dart` | 状态机脚本装载 | 尚可保留 | `conversation_state_kernel/` 的脚本后端 |
| `skill_manifest.dart` | execution shell 与 skill 元数据 | 需扩展 | `domain_policy_bundle/` |

---

## 7. 未来会话必须遵守的设计约束

- 不能新增第二条用户态主总线。
- 不能再让 UI 直接消费内部 trace 作为主逻辑。
- 不能再把 envelope 重新塞回展示层。
- 不能把默认处理继续写回 provider 层。
- 不能让 skill 直接绕开默认基座。
- 不能在多个层里分别维护第二份 authority/source/route/slot 规则。

---

## 8. 建议的新会话恢复流程

### 8.1 先读哪些文件

建议每个里程碑会话按以下顺序恢复上下文：

1. `docs/personal-assistant/assistant-rebuild-roadmap-v1.md`
2. `docs/personal-assistant/assistant-rebuild-design-context-v1.md`
3. `docs/personal-assistant/assistant-rebuild-session-prompts-v1.md`
4. 当前里程碑涉及的代码热点文件

### 8.2 先看哪些代码

最常用的恢复入口：

- `quwoquan_app/lib/personal_assistant/engine/agent_loop.dart`
- `quwoquan_app/lib/personal_assistant/engine/react_runtime.dart`
- `quwoquan_app/lib/personal_assistant/engine/llm_provider.dart`
- `quwoquan_app/lib/personal_assistant/app/capability_gateway.dart`
- `quwoquan_app/lib/ui/chat/pages/chat_detail_page.dart`
- `quwoquan_app/lib/personal_assistant/tools/websearch_tool.dart`

### 8.3 先跑哪些问题

最小真实联调集合：

- 简单事实型：
  - `深圳天气怎么样？顺便告诉我今天出门要不要带伞。`
- 复杂规划型：
  - `这周末去深圳两天，帮我看看住哪里更方便，预算 500 到 700 一晚，最好地铁方便，顺便给我一个轻松一点的两天行程。`
- 上下文承接型：
  - 在住宿问题后继续追问：`如果我更在意夜间安静和第二天去福田通勤方便，住哪一带更合适？`

### 8.4 每个里程碑结束要留下什么

后续会话快速恢复上下文时，最依赖这几类信息：

- 本里程碑改了哪些契约
- 当前仍未解决的风险
- 真实联调结果如何
- 是否需要调整后续里程碑边界

建议每个里程碑结束时最少回写：

- `assistant-rebuild-roadmap-v1.md` 中的状态
- 当前会话结论摘要
- 新增或调整的关键入口文件

---

## 9. 当前里程碑推进的总原则

- 先做结构收口，再做能力增强。
- 先保证默认基座，再做 skill overlay。
- 先保证证据系统，再做引用体验。
- 先切断内部串味，再优化叙事语气。
- 先建立唯一主链，再清理 legacy。

---

## 10. 最终定义的“重构完成”

只有同时满足以下条件，才算这轮脱胎换骨完成：

- 用户态过程链只有一条主线。
- 最终展示链和机器 envelope 完全分账。
- 默认处理在无模型/无网场景下仍有最小质量。
- skill 基于基座扩展，而不是另起炉灶。
- 关键结论和引用源存在稳定绑定。
- 追问、补查、部分回答、重规划成为统一状态机决策。
- 旧并行协议、重复适配层和补丁式兼容桥已显著清退。

