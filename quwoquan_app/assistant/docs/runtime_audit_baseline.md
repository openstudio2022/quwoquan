# 小趣私人助理 Runtime 残留审计基线

> **版本**：v1.1 · **日期**：2026-03-17  
> **用途**：记录本轮字符串治理后的当前残留面，作为 metadata/codegen 与目录重构阶段的统一迁移基线。  
> **从属**：`PERSONAL_ASSISTANT_DESIGN_AND_CONSTRAINTS.md`

---

## 一、审计结论

当前个人助理链路已完成 canonical `AssistantJourney` 切换，`processJournal / uiProcessTimeline / explainableFlow` 兼容主链已删除，但尚未达到“runtime 只消费 typed contract + metadata + generated code”的最终状态。

已经明显收口的部分：

- `assistant_turn` 主契约已通过 `lib/assistant/contracts/assistant_turn_contract.dart` 收口到 `lib/assistant/generated/contracts/assistant_turn.g.dart`
- `ProblemClass`、`AnswerShape`、`FreshnessNeed`、`PlannerPhaseId` 等值域已有 typed enum 入口
- 默认处理链中的一部分兜底文案已集中到 `default_processing_copy_bank.dart`
- `skills/*.dart` 相较 `engine/app/tools` 已更接近 metadata-first 形态

当前最大的残留问题不在 skill，而在 runtime 核心和用户态过程链路：

- `local_phase_execution_owner.dart` 与 phase pipeline 仍是本地执行链路的 payload 消费中枢
- `react_runtime.dart` 仍保留工具名子串判断和原始 JSON 文本读取；流式真相源已收口到运行时事件通道，JSON 只保留稳态结果，此处残留主要是兼容读取路径
- `assistant_journey_projector.dart`、`assistant_stream_projector.dart` 已接管用户旅程投影，但仍需继续压缩共享 sanitization 与协议适配逻辑
- `problem_framer.dart`、`retrieval_planner.dart`、`context_orchestrator.dart` 仍保留部分 query 拆解与检索 IA

---

## 二、热点分层

### A. 优先迁入 metadata / generated contract

以下残留属于“协议或策略本应由 metadata/codegen 承担”的内容：

- `lib/assistant/orchestration/local_phase_execution_owner.dart`
  - 直接读取 `answerPayload['...']`、`parsed['...']`、`payload['...']`
  - 直接读取 `decision`、`messageKind`、`phaseId`、`actionCode`、`reasonCode`
- `lib/personal_assistant/engine/react_runtime.dart`
  - 直接解析原始 JSON 里的 `decision`、`toolCalls`、`searchPlans`、`queryNormalization`
- `lib/personal_assistant/engine/default_processing/problem_framer.dart`
  - 仍承载一部分结构化 query frame 规则
- `lib/personal_assistant/engine/default_processing/retrieval_planner.dart`
  - 仍承载 query task label、query 拼装、answer shape 相关检索 IA
- `lib/personal_assistant/engine/context_orchestrator.dart`
  - 仍承载 slot fill 指令与 context signal 组织逻辑

这些文件在 metadata/codegen 阶段的目标是：

- 把 `map['fieldName']` 收缩到 parser / adapter 边界
- 把协议字段访问替换为 generated DTO / accessor / validator
- 把 query task、query normalization、phase/action/reason 等结构回收到业务对象 metadata

### B. 优先抽共享 sanitizer / policy

以下残留属于“兼容边界或 UI 防泄漏策略”，不应继续散在多处：

- `lib/assistant/application/local_assistant_entry.dart`
- `lib/assistant/application/remote_assistant_entry.dart`
- `lib/assistant/application/assistant_stream_projector.dart`
- `lib/assistant/application/assistant_journey_projector.dart`
- `lib/ui/chat/pages/chat_detail_page.dart`

这些文件当前仍重复维护：

- `contractId`
- `assistant_turn`
- `tool_call`
- `machineEnvelope`
- 各类 JSON envelope 泄漏过滤片段

后续应收口成共享 sanitizer / filter policy，而不是继续在每层复制一份黑名单。

### C. 允许短期保留于迁移 adapter

以下部分短期内可作为迁移 adapter 保留，但必须有退出路径：

- `lib/assistant/contracts/assistant_turn_contract.dart`
- `lib/assistant/contracts/runtime_enums.dart`
- `lib/assistant/contracts/planner_contracts.dart`
- `lib/assistant/contracts/search_plan_contract.dart`
- `lib/assistant/contracts/run_artifacts.dart`

这些文件是当前 compatibility wrapper 边界，但未来目标不是继续扩写，而是逐步由：

- `quwoquan_service/contracts/metadata/assistant/{business_object}/`
- `quwoquan_app/lib/assistant/generated/`

所生成的产物替换。

---

## 三、按治理类型分类

### 1. 用户可见文案残留

集中热点：

- `lib/assistant/application/assistant_journey_projector.dart`
- `lib/assistant/application/assistant_stream_projector.dart`
- `lib/personal_assistant/tools/websearch_tool.dart`
- `lib/personal_assistant/tools/web_fetch_tool.dart`
- `lib/personal_assistant/tools/app_action_tool.dart`

治理目标：

- 工具 phase 文案统一下沉到 `assets/assistant/tools/catalog/tool_catalog.meta.json`
- 通用过程文案逐步迁移到 prompt asset / metadata 模板层
- tool 层仅返回结构化状态与错误码，不再直接承载中文用户话术

### 2. 字符串语义路由残留

集中热点：

- `lib/personal_assistant/engine/react_runtime.dart`
- `lib/assistant/application/assistant_journey_projector.dart`
- `lib/assistant/tool/runtime/tool_metadata_registry.dart`
- `lib/personal_assistant/engine/device_capability.dart`

典型模式：

- `contains('search')`
- `contains('fetch')`
- `contains('retrieval')`
- capability name 子串判断

治理目标：

- 改为消费 tool metadata / capability tag / generated enum
- 不再以名称子串作为工具语义分类依据

### 3. 直接协议字段访问残留

集中热点：

- `lib/assistant/orchestration/local_phase_execution_owner.dart`
- `lib/personal_assistant/engine/react_runtime.dart`
- `lib/personal_assistant/engine/conversation_state_kernel.dart`

治理目标：

- 仅 parser / adapter 可直接访问原始字段
- orchestrator / assessor / UI shaping 统一消费 generated typed API

---

## 四、迁移顺序基线

后续所有治理按以下顺序推进：

1. 冻结文档、SSOT、generated-only 门禁
2. 以 metadata 生成 enum 与闭合小 DTO
3. 先替换最常用的 typed contract 消费点
4. 再拆开放结构：`assistant_turn`、`understanding_result`、`task_graph`、`run_artifacts`
5. 再收口 sanitizer / process copy / tool copy
6. 最后做目录重构与云侧 assistant-service 承接

---

## 五、与目录重构的关系

本文件只定义“当前残留面”，不定义最终目录。

最终目录以以下原则为准：

- shared metadata：`quwoquan_service/contracts/metadata/assistant/{business_object}/`
- 端侧 generated：`quwoquan_app/lib/assistant/generated/`
- 端侧 edge assistant：`quwoquan_app/lib/assistant/{application,domain,orchestration,capabilities,infrastructure}/`
- 端侧 cloud client：`quwoquan_app/lib/cloud/services/assistant/`
- 端侧 UI：`quwoquan_app/lib/ui/assistant/`
- 云侧完整版：预留 `quwoquan_service/services/assistant-service/`

若后续目录重构与本文件列出的热点冲突，优先以 metadata 真相源与 generated 产物替换现有手写实现。
