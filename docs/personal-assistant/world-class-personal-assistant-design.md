# 小趣个人私人助手完整设计总览（World-Class）

## 1. 目标与定位

小趣私人助手从“应用内功能点”升级为“全站中枢能力”，目标是同时达到：

- 世界水准稳定性：可解释、可回放、可灰度、可回滚
- 世界水准体验：持续反馈、精美输出、失败可恢复
- 世界水准扩展性：Plugin + Skill + 多 Agent 统一编排

核心定位：`OpenClaw 协议外壳 + Nanobot 执行内核 + 小趣场景化体验`。

---

## 2. 历史设计演进（已查阅文档汇总）

### 2.1 基线期（2026-02-14）

- 文档：
  - `openspec/changes/archive/2026-02-14-assistant-baseline-spec/proposal.md`
  - `openspec/changes/archive/2026-02-14-assistant-baseline-spec/design.md`
  - `openspec/changes/archive/2026-02-14-assistant-baseline-spec/tasks.md`
- 关键结论：
  - 建立助手入口基线：半弹窗 -> 完整会话
  - 建立浏览信息 `VisitTarget/VisitRecord` 与本地持久化
  - 统一打开上下文 `AssistantOpenContext`

### 2.2 AI Native 引擎期（2026-02-17）

- 文档：
  - `openspec/changes/archive/2026-02-17-personal-assistant-ai-native-v1/proposal.md`
  - `openspec/changes/archive/2026-02-17-personal-assistant-ai-native-v1/design.md`
  - `openspec/changes/archive/2026-02-17-personal-assistant-ai-native-v1/tasks.md`
- 关键结论：
  - 固化 `AgentLoop + ReAct` 内核
  - 引入声明式 Skill Runtime、Tool Registry、Model 路由
  - 统一外部网关（OpenClaw/飞书等渠道）

### 2.3 商用化治理期（2026-02-17）

- 文档：
  - `openspec/changes/archive/2026-02-17-personal-assistant-commercial-v1/design.md`
  - `openspec/changes/archive/2026-02-17-personal-assistant-commercial-v1/tasks.md`
  - `quwoquan_app/personal_assistant/docs/assistent_v1_commercial_spec.md`
- 关键结论：
  - `/v1/assistent/*` 商用接口冻结
  - Provider/Adapter/SLO/告警/降级闭环建立
  - 审计、成本与运行治理进入产品主线

### 2.4 协议升级期（assistant-run-learning）

- 文档：
  - `specs/feature-tree/assistant-run-learning/spec.md`
  - `specs/feature-tree/assistant-run-learning/README.md`
  - `specs/feature-tree/assistant-run-learning/run-stream-policy/run-sync-contract/assistant-run-io-contract/spec.md`
  - `specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/spec.md`
  - `specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/design.md`
  - `specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/tasks.md`
- 关键结论：
  - `assistant_turn_v2` + `tool_observation_v1` + `subagent_*` 成为主协议
  - 明确 `md + json` 双通道
  - 将 Prompt/Skill/Tool/Connector 平台化作为下一阶段核心

### 2.5 对标与总方案收敛

- 文档：
  - `specs/product/assistant-strategy-and-upgrade-analysis.md`
  - `quwoquan_app/personal_assistant/docs/openclaw_capability_migration_audit.md`
  - `quwoquan_app/personal_assistant/docs/openclaw_feishu_integration.md`
- 关键结论：
  - 已具备 OpenClaw 双向互操作能力面
  - 仍需彻底清理 `llm_provider` 中字符串规则残留
  - 多 Agent 与统一编排仍需进一步收敛

---

## 3. 当前系统目标架构

```text
UI(聊天/时间线/动作卡片)
  -> Conversation Orchestrator
  -> Agent Runtime Kernel (Main Agent)
  -> Subagent Scheduler
  -> Tool Fabric (ToolRegistry + Policy + Errors)
  -> Memory (Session + Long-term)
  -> Backends (Local / Remote OpenClaw-compatible)
```

### 3.1 核心边界

- `AgentLoop`：总调度、回合管理、汇总与结构化输出
- `ReactRuntime`：执行循环（reason -> tool -> observe -> replan）
- `ToolRegistry`：工具 schema 校验、统一执行、统一错误封装
- `CapabilityGateway`：`localOnly/remotePreferred/hybrid` 容错路由
- `Skill Runtime`：按 Skill 选择策略与执行约束

---

## 4. 统一协议设计（强约束）

### 4.1 回合协议：`assistant_turn_v2`

每轮必须双轨输出：

- 机器轨 JSON：`decision/slotState/toolCalls/askUser`
- 用户轨 Markdown：`userMarkdown`（进度或最终卡片）

### 4.2 工具观察：`tool_observation_v1`

必须结构化返回：

- `ok/status/errorCode/failureKind/recovery action/slotDelta/data`
- 禁止决策依赖中文文案字符串 `contains(...)`

### 4.3 子代理协议

- `subagent_plan_v1`：goal、budget、timeout、tool whitelist
- `subagent_result_v1`：status、findings、evidence、nextAction

---

## 5. Plugin + Skill 扩展模型（世界水准）

## 5.1 Plugin（Tool）扩展

每个工具是标准插件单元，统一接入 `ToolRegistry`：

- 必须有输入/输出 schema
- 必须有权限与风险声明
- 必须有错误码映射
- 必须写 trace/audit

## 5.2 Skill 扩展（MD-first）

采用 `SKILL.md` 为核心（模型可理解）：

- Frontmatter：`name/description/domain/allowed_tools/trigger_keywords/output_contract/tool_observation_contract/reference_docs/script_guides/dialogue_state_docs`
- 正文：触发、流程、恢复、输出约束
- 可引用附件（按需加载），但避免重 DSL

## 5.3 Prompt Stack（X1）

分层策略：

1. global system
2. runtime policy
3. domain skill
4. recovery
5. output contract

每层可版本化与灰度，不改业务代码。

---

## 6. 多 Skill / 多 Agent 统一编排能力

## 6.1 编排原则

- 先规划，再执行，不直接答复
- 支持并行任务图（DAG）与依赖顺序
- 主 Agent 负责仲裁，不做所有子任务细节

## 6.2 执行层级

- 主 Agent：全局规划、冲突消解、最终汇总
- Skill Agent：垂类任务执行（天气/运势/出行等）
- Micro Agent（可选）：Skill 内子步骤（定位、检索、建议生成）

## 6.3 汇总机制

汇总必须做三件事：

- 证据合并与去重
- 冲突检测与可信度打分
- 最终双轨输出（JSON 决策 + Markdown 展示）

---

## 7. 关键场景：天气与运势的统一执行链

### 7.1 城市槽位获取顺序

1. 当前 query 提取城市  
2. 历史会话/长期记忆补全  
3. `local_context` 获取 GPS  
4. `local_context`（位置能力）获取城市或经纬度  
5. 最后追问用户

### 7.2 双轨输出要求

- `tool_call` 轮：JSON 给 `toolCalls`（数组，每项指明工具与参数）；Markdown 给进度说明
- `answer` 轮：JSON 标记完成；Markdown 给精美结果卡片

---

## 8. 稳定性与治理门禁

## 8.1 代码层门禁

- 禁止在关键决策层新增 `contains("中文文案")`
- 决策层文案必须 i18n key 化
- 生成文件禁止手改（DO NOT EDIT）

## 8.2 质量门禁

- `decision_parse_success >= 99.5%`
- `render_fallback_rate < 1%`
- 三路一致性：`remotePreferred/hybrid/localOnly`

## 8.3 发布门禁

- 灰度：10% -> 50% -> 100%
- 任一核心指标劣化触发回滚

---

## 9. 当前差距（必须直面）

基于现状审阅，仍存在：

- `HeuristicLocalLlmProvider` 中残留大量写死规则与固定文案
- 天气等垂类仍有 regex/contains 决策残留
- `SKILL.md` 已接入但尚未完全成为唯一决策来源
- 多 Agent 编排已有框架但尚未全面覆盖多 skill 融合场景

这解释了“部分问题仍返回固定隐私文案”与“垂类规则未完全清理”。

---

## 10. 实施路线（对齐 X1/X2，X3/X4 预留）

### Phase A（立即）

- 完成 X1 Prompt Stack 主链路化
- 完成 X2 Skill MD-first 标准化
- 将天气/运势迁移到 Skill 驱动，移除 provider 内写死分支

### Phase B

- 扩展到多 skill 编排（主 Agent + Skill Agent）
- 强化 evidence 汇总与冲突闭合
- 完成 i18n key 全链路

### Phase C

- 私有 connector 规范化（X3）
- 质量与成本看板（X4）

---

## 11. 结论

小趣私人助手的正确目标态不是“继续堆规则判断”，而是：

- 协议化：统一机器可执行协议
- 平台化：Prompt/Skill/Tool 可扩展治理
- 编排化：多 Skill、多 Agent 可组合
- 产品化：稳定、精美、可信、可持续演进

本目录文档用于后续评审与开发统一基线，避免再次回到“局部修补 + 规则分叉”。

## 12. 与新规范的关系

本设计总览用于讲清“为什么这样做”，具体执行与交付以以下新规范为准：

- `docs/personal-assistant/personal-assistant-fullstack-standard.md`
- `quwoquan_app/personal_assistant/docs/skill_development_standard.md`

两份规范共同约束：全流程、交付件格式、协议契约、测试门禁与回填口径。
