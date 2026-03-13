# 小趣助手脱胎换骨重构：5 个新会话启动提示词（Session Prompts v1）

## 使用说明

你后续每开启一个新会话，只复制对应里程碑的提示词即可。

通用要求：

- 只做当前里程碑，不提前做后续里程碑。
- 开始前必须先读：
  - `docs/personal-assistant/assistant-rebuild-roadmap-v1.md`
  - `docs/personal-assistant/assistant-rebuild-design-context-v1.md`
- 结束时必须：
  - 更新路标文档中的状态
  - 说明改了哪些契约/模块
  - 说明未解决风险
  - 跑目标回归和真实联调

---

## 里程碑 1 启动提示词

```text
请只完成“小趣助手脱胎换骨重构”的里程碑 1：核心契约冻结 + 单一过程总线。

开始前先阅读：
- docs/personal-assistant/assistant-rebuild-roadmap-v1.md
- docs/personal-assistant/assistant-rebuild-design-context-v1.md

本里程碑目标：
- 冻结核心契约：RunArtifacts、ProcessJournalEvent、TraceVisibility、EvidenceLedgerEntry、SlotStateSnapshot、DomainPolicyBundle
- 统一用户态过程总线，只保留一条主链
- 给 summarize_session、记忆提炼、内部分域分类、内部补救 trace 加可见性隔离，禁止进入用户可见过程流
- 旧协议可以保留兼容桥，但不再作为主数据源

必须重点检查的文件：
- quwoquan_app/lib/personal_assistant/engine/agent_loop.dart
- quwoquan_app/lib/personal_assistant/app/capability_gateway.dart
- quwoquan_app/lib/ui/chat/pages/chat_detail_page.dart

严格边界：
- 不开始做最终展示收口
- 不开始做 BaselineKernel
- 不开始做 RetrievalBroker
- 不开始做 skill overlay

必须达成的结果：
- 用户过程里不再出现内部摘要/压缩任务串味
- 非 thinking 的 processReplace 归零
- 用户态过程协议形成唯一主入口

必须验证：
- 目标回归测试
- 至少一次真实问题联调（深圳天气）

结束时请输出：
1. 本里程碑完成了什么
2. 修改了哪些契约/文件
3. 还剩什么风险
4. 是否已更新 docs/personal-assistant/assistant-rebuild-roadmap-v1.md
```

---

## 里程碑 2 启动提示词

```text
请只完成“小趣助手脱胎换骨重构”的里程碑 2：输出双账 + 最终收口 + append-only 持久化。

开始前先阅读：
- docs/personal-assistant/assistant-rebuild-roadmap-v1.md
- docs/personal-assistant/assistant-rebuild-design-context-v1.md

本里程碑目标：
- 分离 machineEnvelope、displayMarkdown、displayPlainText
- 让 CompletedArtifact 成为最终展示与存储收口对象
- UI 和 storage 不再直接信任 finalText
- uiProcessTimelineV2 改为直接持久化 append-only process journal，而不是结束后重建
- session/memory/summary 统一只读取 displayPlainText

必须重点检查的文件：
- quwoquan_app/lib/personal_assistant/engine/agent_loop.dart
- quwoquan_app/lib/personal_assistant/protocol/run_response.dart
- quwoquan_app/lib/personal_assistant/engine/llm_response_parser.dart
- quwoquan_app/lib/ui/chat/pages/chat_detail_page.dart

严格边界：
- 不做 BaselineKernel
- 不做 RetrievalBroker
- 不做 skill overlay
- 不做 legacy 清退

必须达成的结果：
- 最终展示内容不再出现 assistant_turn_v4 / contractVersion / JSON envelope
- 不再“流式说一遍，完成再刷一遍”
- 持久化 timeline 条数接近流式 commit 数量，不再被压成少量 summary

必须验证：
- 目标回归测试
- 至少两次真实问题联调：深圳天气、深圳住宿/行程

结束时请输出：
1. 双账和最终收口如何落地
2. timeline 持久化语义是否已改为 append-only
3. 是否还存在 JSON 泄漏或二次刷新风险
4. 是否已更新 docs/personal-assistant/assistant-rebuild-roadmap-v1.md
```

---

## 里程碑 3 启动提示词

```text
请只完成“小趣助手脱胎换骨重构”的里程碑 3：默认处理基座化 + 检索 Broker + 证据账。

开始前先阅读：
- docs/personal-assistant/assistant-rebuild-roadmap-v1.md
- docs/personal-assistant/assistant-rebuild-design-context-v1.md

本里程碑目标：
- 把当前 HeuristicLocalLlmProvider 中的规则型意图/规划/成答迁成 BaselineKernel
- 建立 RetrievalBroker，负责 provider 快速 failover、queryTasks 并行、authority/source policy
- 建立 EvidenceLedger，统一记录证据、权威度、时效性、相关性、槽位贡献
- 建立默认兜底质量门槛：F0/F1/F2/F3

必须重点检查的文件：
- quwoquan_app/lib/personal_assistant/engine/llm_provider.dart
- quwoquan_app/lib/personal_assistant/tools/websearch_tool.dart
- quwoquan_app/lib/personal_assistant/engine/react_runtime.dart
- quwoquan_app/lib/personal_assistant/engine/agent_loop.dart

严格边界：
- 不做 skill overlay
- 不做状态机收编
- 不做最终 legacy 清退

必须达成的结果：
- 无模型/无网/检索失败时，不再只吐一句失败提示
- provider 失败时能自动快速切换，而不是慢慢重试或直接裸失败
- 有资料时必须形成最基本的 evidence ledger
- 复杂规划型问题最差也要输出维度框架或澄清问题

必须验证：
- 目标回归测试
- 真实问题联调：
  - 深圳天气
  - 深圳住宿/行程
  - 检索失败/无模型场景

结束时请输出：
1. BaselineKernel 是否已经成为默认处理主基座
2. RetrievalBroker 和 EvidenceLedger 如何落地
3. 默认兜底最低质量是否达标
4. 是否已更新 docs/personal-assistant/assistant-rebuild-roadmap-v1.md
```

---

## 里程碑 4 启动提示词

```text
请只完成“小趣助手脱胎换骨重构”的里程碑 4：槽位/状态内核 + DomainPolicyBundle + skill overlay。

开始前先阅读：
- docs/personal-assistant/assistant-rebuild-roadmap-v1.md
- docs/personal-assistant/assistant-rebuild-design-context-v1.md

本里程碑目标：
- 引入 typed SlotState
- 引入 ConversationStateKernel
- 将 SkillExecutionShell、DialogueRoundScript、fallback_general_search 统一收编到 DomainPolicyBundle
- 建立 skill overlay 机制：默认基座提供通用能力，skill 只做增量覆盖

必须重点检查的文件：
- quwoquan_app/lib/personal_assistant/skills/skill_manifest.dart
- quwoquan_app/lib/personal_assistant/engine/dialogue_state_runtime.dart
- quwoquan_app/lib/personal_assistant/contracts/skill_run.dart
- quwoquan_app/lib/personal_assistant/contracts/aggregation_state.dart
- quwoquan_app/lib/personal_assistant/engine/agent_loop.dart

严格边界：
- 不开始做最终答案/叙事统一引擎
- 不开始做 legacy 清退

必须达成的结果：
- 槽位状态、追问、部分回答、重规划成为统一内核决策
- weather、fallback_general_search、travel/lodging 至少三类域基于同一主流程运行
- skill 不能绕过默认处理质量底线
- 追问场景能承接上下文，不再重置

必须验证：
- 目标回归测试
- 真实问题联调：
  - 深圳天气
  - 深圳住宿/行程
  - 住宿追问承接

结束时请输出：
1. SlotState / ConversationStateKernel / DomainPolicyBundle 如何落地
2. skill overlay 是否已经建立在默认基座之上
3. 追问与部分回答是否统一到状态机内核
4. 是否已更新 docs/personal-assistant/assistant-rebuild-roadmap-v1.md
```

---

## 里程碑 5 启动提示词

```text
请只完成“小趣助手脱胎换骨重构”的里程碑 5：答案/叙事统一引擎 + 引用绑定 + legacy 清退 + 总体验收。

开始前先阅读：
- docs/personal-assistant/assistant-rebuild-roadmap-v1.md
- docs/personal-assistant/assistant-rebuild-design-context-v1.md

本里程碑目标：
- 统一 AnswerComposer 与 NarrativeEngine
- 建立 claim-to-evidence 绑定
- 支持 inline evidence links / 🔗
- 统一资料展开与过程挂载渲染
- 清退 phaseTimeline、userPhaseEvent、processUpdate 等 legacy 主职责
- 完成最终真实联调验收

必须重点检查的文件：
- quwoquan_app/lib/personal_assistant/engine/agent_loop.dart
- quwoquan_app/lib/personal_assistant/app/capability_gateway.dart
- quwoquan_app/lib/ui/chat/pages/chat_detail_page.dart
- quwoquan_app/lib/ui/chat/widgets/message/assistant_process_drawer.dart
- quwoquan_app/lib/ui/chat/widgets/message/chat_message_bubble.dart

严格边界：
- 不再新增大功能
- 重点是统一体验和结构清理

必须达成的结果：
- 关键结论可以绑定到对应证据源
- 无证据时仍然结构清楚、逻辑完整、可执行
- 旧并行协议和重复适配层的主职责被清退
- 代码结构能清楚回答：默认处理在哪、skill overlay 在哪、证据在哪、状态机在哪、用户过程主链在哪

必须验证：
- 全量目标回归
- 真实问题联调：
  - 深圳天气
  - 深圳住宿/行程
  - 住宿追问承接
  - 无模型
  - 无网/检索失败

结束时请输出：
1. 最终体验是否完成统一
2. claim-to-evidence 与引用绑定如何落地
3. legacy 清退了哪些主职责
4. 是否已更新 docs/personal-assistant/assistant-rebuild-roadmap-v1.md
```

