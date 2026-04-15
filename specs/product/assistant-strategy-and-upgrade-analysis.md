# 小趣私人助理：业界代码对标与架构升级总方案（全面修订）

> 本文档用于指导小趣私人助理从“可用”升级到“业界一线水准”的端云一体化 Agent 系统。  
> 目标读者：产品、架构、端侧、云侧、算法、测试与渠道集成团队。  
> 适用场景：多人并行开发、跨会话协作、协议先行的工程落地。

---

## 0. 执行摘要（给决策者）

当前小趣已经具备商业级雏形（C 位入口、ReAct 循环、工具总线、远端优先+本地回退、渠道桥接），但核心短板是：

1. **决策层仍混入字符串分支**（脆弱、不可国际化、不可扩展）  
2. **工具观察缺少强结构协议**（失败恢复与补槽不稳定）  
3. **领域状态机资产未完全进入主执行链路**（“有设计、弱执行”）  
4. **多 Agent 能力缺少统一调度与 UI 语义**（无法稳定扩展复杂任务）  
5. **Skill/Prompt/Tool 的扩展契约尚不统一**（并行研发容易分叉）

本次升级建议：以 **协议驱动 Agent Runtime** 为核心，统一 `json 决策 + markdown 展示` 双通道，构建主 Agent + Subagent 调度中枢，并将 Prompt、Skill、Tool、私有数据接入纳入同一扩展框架。

---

## 1. 业界代码实现可借鉴点（源码机制视角）

> 说明：本节按“代码实现机制”抽象，不依赖产品宣传口径。  
> 对标对象：OpenClaw 类远端 Agent 服务实现、Nanobot 类通用 Agent 内核、主流 Assistant/Agent Runtime 实践。

### 1.1 OpenClaw 类实现：强在“统一 run 协议 + 流式事件 + 远端优先容错”

典型机制：

- 单一入口：`/v1/run`、`/v1/run/stream`
- 流式事件：`trace/chunk/completed/failed`
- 统一结果契约：可被 UI 与渠道直接消费
- 远端执行失败时回退本地执行器
- 渠道互操作：skills list/invoke/run 均可外部集成

可借鉴优点：

1. **主路径流式可解释**（不仅有最终答复，还有过程事件）  
2. **协议统一降低接入成本**（APP、OpenClaw、飞书同一能力面）  
3. **容错路径清晰**（远端失败不等于服务不可用）

### 1.2 Nanobot 类实现：强在“通用 Agent 内核 + 工具治理 + 子任务自治”

典型机制：

- `AgentLoop` 单循环调度：消息 -> 模型 -> 工具 -> 观察 -> 下一轮
- `ToolRegistry` 做 schema 校验、统一执行、统一错误封装
- `Session + Memory` 做历史持久化与 consolidation
- `Subagent` 处理复杂任务并回注主会话
- 渠道层与核心执行层解耦

可借鉴优点：

1. **执行内核稳定**（模型与工具、渠道、存储解耦）  
2. **复杂任务可拆分并发**（主对话不阻塞）  
3. **长期记忆可治理**（不是无限堆消息）

### 1.3 一线 Assistant/Agent Runtime 共性

| 共性能力 | 工程体现 |
|---|---|
| 协议优先 | 模型输出可执行 JSON，不依赖字符串 |
| 事件驱动 | trace/chunk/tool/subagent 统一事件总线 |
| 安全默认 | 工具权限、风险分级、用户确认点 |
| 可回放可审计 | runId/traceId/toolCallId 全链路 |
| 扩展友好 | prompt/skill/tool/connector 插件化 |

---

## 2. 小趣当前能力盘点（基于现代码）

### 2.1 已具备的高价值能力

- C 位入口与全站会话中枢
- 端侧 `AgentLoop + ReactRuntime` 循环
- `CapabilityGateway`（`localOnly/remotePreferred/hybrid`）
- 工具总线（检索、本地上下文、媒体、intent）
- 结构化响应字段（含 markdown 载体）
- 学习闭环、会话持久化、trace 机制

### 2.2 当前关键 gap（必须正面解决）

1. 决策分支仍有 `contains(...)` 字符串判断  
2. 工具错误语义不统一，缺少机器可执行恢复协议  
3. 领域对话资产（天气等）未完全接入主执行协议  
4. i18n 停留在展示层，未进入“决策层 key 化”  
5. Subagent 缺位：复杂任务只能串行阻塞主回合

---

## 3. 目标架构：从“对话功能”升级为“Agent 平台”

```text
[UI Layer]
Chat / Timeline / ActionCards / TracePanel / SubagentPanel
        |
        v
[Conversation Orchestrator]
Turn Manager + Slot State + Policy Guard + Locale Resolver
        |
        v
[Agent Runtime Kernel]
Planner -> Act -> Observe -> Reflect/Replan
MainAgent + Subagent Scheduler
        |
        v
[Tool Fabric]
ToolRegistry + SchemaValidator + ErrorNormalizer + PermissionGate
        |
        v
[Memory & Context]
Session Store + Working Memory + Long-term Memory + Consolidation
        |
        v
[Execution Backend]
Local Engine <-> Remote Engine (OpenClaw/Cloud)
(shared protocol, shared trace semantics)
```

核心原则：

- **协议先于实现**
- **默认安全，最小权限**
- **本地可用，远端增强**
- **可观测、可回放、可灰度**

---

## 4. 交互协议升级（必须落地）

## 4.1 统一回合协议：`assistant_turn_v2`

每轮模型必须返回两个通道：

1. **machine channel (JSON)**：程序执行
2. **user channel (markdown)**：用户展示

示例结构（简化）：

```json
{
  "contract_version": "assistant_turn_v2",
  "decision": {
    "next_action": "tool_call",
    "reason_code": "weather_need_realtime_evidence"
  },
  "slot_state": {
    "location": { "status": "missing", "source": "none", "confidence": 0.0 },
    "time_range": { "status": "filled", "value": "today", "source": "query", "confidence": 0.9 }
  },
  "toolCalls": [
    {
      "tool_name": "local_context",
      "args": {},
      "retry_policy": { "max_retries": 1, "backoff_ms": 300 }
    }
  ],
  "ask_user": {
    "required": false,
    "slot_id": "",
    "question_l10n_key": "",
    "question_args": {}
  },
  "user_markdown": "## 正在获取本地城市\n- 我先尝试获取你的城市信息，以便给出更准确天气。"
}
```

### 4.2 工具观察协议：`tool_observation_v1`

禁止仅用 `message` 字符串做判定，统一结构：

```json
{
  "tool_name": "unified_retrieval",
  "ok": false,
  "error_code": "ASSISTANT.MIDDLEWARE.upstream_timeout",
  "error_class": "timeout",
  "retryable": true,
  "slot_delta": { "location": null, "weather_summary": null },
  "i18n_key": "assistant.error.upstream_timeout"
}
```

### 4.3 失败恢复协议：`recovery_decision_v1`

模型依据 `tool_observation` 与历史状态决定：

- `retry_tool`
- `ask_user`（补槽）
- `fallback_answer`（有边界声明）

---

## 5. Subagent 架构（复杂任务必须能力）

## 5.1 何时启用 Subagent

满足任一条件时：

- 多源并发检索/比对
- 长链路任务（>1 回合且可分治）
- 高延迟外部系统调用
- 主会话需要“边回答边执行后台任务”

### 5.2 Subagent 协议

#### `subagent_plan_v1`

```json
{
  "task_id": "t-001",
  "goal": "收集深圳未来24小时天气与预警",
  "budget": { "max_steps": 8, "timeout_ms": 12000 },
  "tool_whitelist": ["unified_retrieval", "web_search"],
  "output_contract": "subagent_result_v1"
}
```

#### `subagent_result_v1`

```json
{
  "task_id": "t-001",
  "status": "success",
  "findings": [{"key": "weather_now", "value": "多云 26C"}],
  "evidence": [{"source": "nmc.cn", "freshness_hours": 0.5}],
  "recommended_next_action": "answer"
}
```

### 5.3 UI 渲染要求

- 主气泡可先给“阶段性答复”
- 子任务以 timeline 显示 `started/running/completed/failed`
- 用户可中断、重试、忽略某子任务结果

---

## 6. Prompt 与 Skill 扩展框架（系统化）

## 6.1 Prompt Stack（分层治理）

1. **Global System Prompt**：身份、隐私、真实性、风险边界  
2. **Runtime Policy Prompt**：本轮预算、权限、可用工具、当前槽位  
3. **Domain Skill Prompt**：天气/出行/健康等垂类策略  
4. **Recovery Prompt**：失败恢复策略与追问上限  
5. **Output Contract Prompt**：强制 `assistant_turn_v2`

### 6.2 Skill DSL（建议）

每个垂类 skill 至少包含：

- `skill_manifest.yaml`
- `slot_contract.json`
- `dialogue_policy.md`
- `tool_binding.json`
- `response_style.md`
- `i18n_keys.json`

收益：产品、算法、工程可并行协作，不互相踩线。

---

## 7. 私有数据与工具扩展（企业级能力）

## 7.1 Tool Fabric 标准

每个工具必须声明：

- 输入输出 schema
- 权限模型（user consent / role / channel）
- 隐私分级与脱敏策略
- 错误码映射（metadata errors）
- 审计字段（runId/traceId/toolCallId）

### 7.2 私有数据接入模式

- `connector_tool`：企业系统读写（CRM/工单/知识库）
- `retrieval_tool`：向量检索 + 结构化检索
- `action_tool`：执行动作（发通知/建任务/触发流程）

全部通过策略闸门，不允许绕过。

---

## 8. i18n 与对话文案治理（避免硬编码）

要求：

1. 决策层输出 `l10n_key + args`，程序渲染文案  
2. 工具错误统一映射 metadata 错误码与多语言文案  
3. UI 文案不作为业务判断输入  
4. 禁止 `contains("中文文案")` 决策

---

## 9. 对齐当前仓库的落地路径（分阶段）

### Phase A（P0，协议化止血）

- 引入 `assistant_turn_v2` 与 `tool_observation_v1`
- 清理字符串分支判定
- 先落天气垂类（城市补槽、失败恢复）

**验收**：

- 天气场景 4 条主链稳定：  
  - 城市已知直接答  
  - 无城市先本地定位  
  - 定位失败追问城市  
  - 工具超时按协议恢复

### Phase B（P1，能力升级）

- 接入 Subagent 执行框架（先做检索型任务）
- UI 增加 trace/subagent timeline
- 统一 i18n key 渲染

### Phase C（P2，平台化）

- Skill DSL 平台化
- 私有数据 connector 标准化
- 成本/SLO/质量看板闭环

---

## 10. 并行开发协作规范（指导其它对话同步开发）

## 10.1 模块拆分与责任边界

- **协议组**：定义 `assistant_turn_v2`、`tool_observation_v1`、`subagent_*`
- **运行时组**：AgentLoop/Runtime/PolicyGuard 改造
- **工具组**：ToolRegistry schema 校验与错误归一
- **前端组**：timeline/action card/subagent 渲染
- **垂类组**：weather 等 skill policy 与 prompt stack
- **测试组**：契约测试、回归测试、鲁棒性测试

### 10.2 合并策略

- 先合并协议文档与 schema 文件，再并行实现
- 所有实现 PR 必须引用协议版本
- 破坏性改动必须带 migration strategy

### 10.3 测试矩阵（最低要求）

- 协议解析测试（JSON 严格校验）
- 工具失败恢复测试（timeout/no_data/permission）
- 多语言渲染测试（zh/en）
- Subagent 回注测试
- remote/local 一致性测试

---

## 11. 风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| 协议改造范围大 | 节奏变慢 | 分阶段，先天气垂类试点 |
| 多 Agent 增加复杂度 | 线上不稳定 | 子任务预算、白名单工具、强超时 |
| i18n 接入滞后 | 体验割裂 | 决策层 key 化作为硬门禁 |
| 远端/本地行为漂移 | 调试困难 | 同协议同 trace 语义，增加一致性测试 |

---

## 12. 结论

小趣要达到“既能回答又能干事、可扩展到多 Agent、可接私有数据、可指导多人并行开发”的业界水准，关键不是继续堆 if-else，而是：

1. **协议化（结构化决策与观察）**
2. **调度化（主 Agent + Subagent）**
3. **平台化（Prompt/Skill/Tool 统一扩展框架）**
4. **治理化（i18n、隐私、审计、测试、灰度）**

建议立即以天气垂类为首个试点，在不打断主业务的前提下完成协议化落地，再按 Phase B/C 扩展到全域。

# 小趣私人助理：产品战略转型与升级分析

> 基于当前代码库与 openspec/specs 的审视，分析「小趣 C 位」战略、对话与技能管理现状，并对标 OpenClaw / Google Assistant 给出产品设计与优化建议。

---

## 一、产品战略转型分析：小趣 C 位的意义

### 1.1 当前定位与信息架构

- **核心理念**（app-global）：「以兴趣为半径，画出我们的交集。」趣我圈 = **兴趣锚点 + 智能助手** 的共生系统；小趣 = 星火 (Spark)，Slogan「让兴趣闪亮」。
- **五大频道**：发现、圈子、创作（抽屉）、**小趣（C 位）**、趣聊、我的。
- **实现形态**：
  - 底部导航 index=2 为小趣入口，**不占 IndexedStack 槽位**（`SizedBox.shrink()`），点击后 `context.go('/chat/${assistantConversationId}')`，即跳转到「小趣专属会话」。
  - 中心按钮使用 `PetalMark` 组件，支持 `silent / wake / listening` 三种视觉状态，从其他 Tab 返回时触发「listening」态 3 秒后回 silent。
  - 小趣 = **全 App 的统一对话入口**，而非独立「助理频道页」；心智是「找小趣」= 进入与小趣的对话。

### 1.2 战略转型含义

| 维度 | 转型前（工具化） | 转型后（C 位私人助理） |
|------|------------------|-------------------------|
| **入口** | 分散（发现悬浮球、趣聊置顶、我的入口） | **底部 C 位**，一次触达、全场景统一 |
| **心智** | 「问小趣」「助手入口」 | **「找小趣」** = 私人助理，随时可对话 |
| **与频道关系** | 附属在发现/聊天/个人之下 | **与发现/圈子/趣聊/我的平级**，且为中枢 |
| **产品重心** | 内容与社交为主，助手为辅 | **助手与内容/社交并重**，甚至以助手串联全站 |

这一放置等同于将「私人助理」提升为与「发现」「趣聊」同级的**一级价值主张**，与「全面升级私人助理」的表述一致：从「功能点」升级为「产品支柱」。

### 1.3 与主流程的衔接

- 从任意 Tab 点 C 位 → 记录 `lastMainTabBeforeAssistantProvider` → 进入小趣会话；返回时回到原 Tab。
- 会话页可携带 `AssistantOpenContext`（如 source=discovery、entityId、hints），实现**上下文继承**（如从某条帖子「找小趣」带帖子信息）。
- 规格上存在「三层交互形态」：帮读卡 / 任务抽屉 / 会话页；当前实现以**会话页**为主，帮读/任务抽屉在发现页等场景的渗透仍可加强。

**结论**：C 位设计已清晰表达「小趣 = 全站私人助理入口」的战略；下一步关键是**对话能力与技能体系**能否支撑用户形成「有事就找小趣」的习惯，否则 C 位会沦为空洞入口。

---

## 二、ReAct 框架在端侧的实现与端云分工

### 2.0 当前架构确认

- **ReAct/Agent 循环所在位置**：完整实现于 **端侧（Flutter App）**。
  - `lib/personal_assistant/engine/agent_loop.dart`：`PersonalAssistantAgentLoop` 负责上下文组装、领域解析、双门禁、规划与综合。
  - `lib/personal_assistant/engine/react_runtime.dart`：`ReactRuntime.run()` 执行多轮「规划 → 工具调用 → 观察 → 下一轮」循环，直至满足停止条件或达到预算。
  - 工具执行（WebSearch、UnifiedRetrieval、LocalContext、MediaGallery、IntentBridge 等）均在端侧通过 `AssistantToolRegistry` 执行。
- **LLM 调用位置**：端侧通过 `SwitchableAssistantLlmProvider` 调用：
  - **本地启发式**：`HeuristicLocalLlmProvider`，无网络，规则/模板驱动，用于离线或降级。
  - **远端 HTTP**：`OpenAiCompatibleLlmProvider`，请求发往配置的 baseUrl（可为自建或第三方 OpenAI 兼容 API），推理在云端，但 **编排与工具链在端侧**。
- **与 OpenClaw 的关系**：`CapabilityGateway` 在 `remotePreferred` 下先调 **OpenClaw 全量接口**（POST `baseUrl/v1/run`），远端返回**整次 run 的完整结果**；若满足 `_isRemoteResponseCommercialReady()` 则直接采用，**不再在端侧跑 ReAct**。只有远端不可用或结果不合格时才回退到端侧 `AssistantGateway.run()`，即端侧完整 ReAct 循环。

因此当前存在两条执行路径：

| 路径 | 触发条件 | ReAct 所在位置 | LLM 所在位置 |
|------|----------|----------------|--------------|
| **远程全量** | remotePreferred 且 OpenClaw 可用且响应合格 | 在 OpenClaw 服务端（或等价实现） | 云端 |
| **端侧回退** | 仅 localOnly，或远端失败/不合格 | 端侧（Dart AgentLoop + ReactRuntime） | 可为本地启发式或远端 HTTP |

云侧（quwoquan_service）当前仅有 `runtime/assistant/qa_runner.go` 的「上下文组装 + 单次 LLM 调用 + 流式输出」，**没有**与端侧等价的 ReAct 多轮工具循环；设计文档中的 assistant-service 更多是「上下文感知 QA + Suggested Actions」，与端侧 ReAct++ 双门禁是两套不同深度的能力。

### 2.0.1 端侧 ReAct 是否合理？

**结论：在「远端优先、端侧回退」的现有策略下，把 ReAct 放在端侧是合理的**，理由如下。

- **离线与弱网**：端侧保留完整 ReAct + 本地启发式 LLM，可在无网或 OpenClaw 不可用时仍给出可用的降级回答，符合「私人助理随时可用」的预期。
- **设备能力与隐私**：工具链中的 LocalContext、IntentBridge、MediaGallery 等依赖设备本地能力（页面上下文、系统意图、相册）；若全部上云，需要把大量本地状态与权限同步到云端，延迟与隐私成本高。端侧编排可只把「必要摘要」传给远端 LLM，而把敏感操作留在本机。
- **迭代与灰度**：端侧 ReAct 与模板、领域路由、双门禁强绑定；在端侧可独立于后端发版做 A/B（如不同模板版本、不同门禁阈值），便于快速实验。
- **成本与扩展**：当 OpenClaw 或自有云 ReAct 成熟后，可逐步把「主路径」迁到云侧，端侧 ReAct 仍可作为回退与离线路径保留，形成「云主端备」的稳定架构。

**需要注意**：端侧 ReAct 依赖端侧 LLM 配置（含远端 API）；若希望「只连一次云」就完成全流程，则需云侧提供与端侧契约一致的「全量 run（含 ReAct+工具）」接口并支持流式，当前 OpenClaw 桥接的是「整次 run 的完整响应」，不是逐 chunk 流式。

### 2.0.2 端侧方案 vs 云侧方案：差异与优缺点

| 维度 | 端侧 ReAct（当前主实现） | 云侧 ReAct（主逻辑在服务端） |
|------|--------------------------|------------------------------|
| **执行位置** | 编排与工具执行在 App 内；LLM 可本地启发或 HTTP 调云 | 编排、工具、LLM 均在服务端；端只发请求、收流/结果 |
| **网络依赖** | 可完全离线（本地启发式）或仅 LLM 用网 | 强依赖网络；离线只能做缓存/预置回复 |
| **首字/流式** | 若 LLM 走 HTTP 流式，端可边收边渲染；当前多为「整段完成后展示」 | 云侧天然适合 SSE/WebSocket 流式，首字延迟易优化 |
| **设备能力** | 直接调系统 API、页面上下文、相册等，无额外同步 | 需把上下文、权限结果等上传，延迟与隐私成本高 |
| **一致性** | 多端需各自维护一份 ReAct+模板，易出现行为差异 | 单点逻辑，多端一致；升级一处即可 |
| **算力与成本** | 推理在云（若用远端 LLM）或省在本地启发式；编排在端，云成本低 | 推理+编排都在云，云成本高；可集中做模型与策略升级 |
| **安全与合规** | 敏感工具在端执行，数据可少上云 | 需严格的数据与权限策略，否则合规压力大 |
| **迭代与发版** | 改 ReAct/模板常需发 App 版；可配合动态配置/模板拉取 | 改逻辑可只发服务端，端只做协议兼容 |
| **可观测与调试** | 端侧日志与 trace 需主动上报才能集中分析 | 全链路在云，日志与 trace 自然集中 |

**端侧方案优点**：离线可用、设备能力与隐私友好、云成本低（编排在端）、可与现有「OpenClaw 全量 + 端侧回退」并存。  
**端侧方案缺点**：流式体验需端侧与 LLM 接口配合、多端逻辑需同步维护、大版本能力升级依赖 App 发版（除非模板/配置拉取）。

**云侧方案优点**：流式与首字延迟易优化、逻辑一致、迭代不依赖 App 发版、可观测集中。  
**云侧方案缺点**：强依赖网络、设备相关能力需上传或代理、云成本与合规要求高。

### 2.0.3 建议的演进方向

- **短期**：保持「远端优先（OpenClaw 全量）+ 端侧 ReAct 回退」，明确双路径的 SLO 与降级策略；在端侧补齐流式消费（若远端或端侧 LLM 支持 stream），避免整段才上屏。
- **中期**：若自有 assistant-service 要提供「完整 ReAct + 工具」能力，可在云侧实现与端侧契约一致的 run/runStream，端侧 CapabilityGateway 优先调该云服务并支持流式；端侧 ReAct 仍保留为离线与回退路径。
- **长期**：云侧承担「主路径」的推理与编排，端侧负责设备工具代理、上下文采集与流式展示；敏感工具继续在端执行，仅把「非敏感编排 + 云端工具」放在云上，形成清晰的端云分工与隐私边界。

---

## 三、ReAct 框架、插件化、Skill 与渠道接入详析及世界级对标

本节基于仓库内 OpenClaw 集成文档、能力迁移审计与代码，详析小趣的 ReAct 框架、插件化、Skill 与渠道能力，并对照世界级参照系给出四维差距与借鉴点。

### 3.1 ReAct 框架详析

**小趣端侧 ReAct 链路**（与 OpenClaw 能力迁移审计对齐）：

- **AgentLoop 多阶段**：`PersonalAssistantAgentLoop` 实现「上下文组装 → 领域解析 → 双门禁（前置/汇总）→ 规划 → 执行 → 综合」；内层 `ReactRuntime.run()` 为经典 ReAct 循环：`reason（LLM）→ buildPlan（解析 tool calls）→ 执行工具 → observe → 下一轮**，直至无 tool call 或达迭代/预算上限。
- **状态与预算**：`ReactRunState` 管理 iteration、toolBudget、stopReason；`ReactPlanner` 将 LLM 输出解析为 `PlanStep`（toolName、arguments、description），由 `_toolRegistry.execute()` 执行。
- **与 OpenClaw 的对应**：审计表将「AgentLoop 多阶段执行」标为与 OpenClaw 对齐的「ReAct++ (Plan/Act/Observe/Reflect/Replan)」；当前实现中 Reflect/Replan 体现在双门禁的 GapFillTask 与补查轮次，而非单文件命名。

**OpenClaw 侧角色**（从集成文档推断）：

- OpenClaw 作为**远端服务**暴露 `POST /v1/run`（及可选 `/v1/run/stream`）；小趣 `CapabilityGateway` 在 remotePreferred 下将整次 run 交给 OpenClaw，由 OpenClaw 内部完成其自身的 Agent/ReAct 或等价流程，返回完整 `AssistantRunResponse`。
- 反向：OpenClaw 可调小趣暴露的 `GET /v1/skills`、`POST /v1/skills/invoke`、`POST /v1/run/stream`，将小趣当作「技能与 run 的提供方」使用，形成**双向互操作**（见 `openclaw_feishu_integration.md`）。

**差距与借鉴**：

- **世界级参照**：Google ADK 已从「意图 + 对话流」演进为 **Agent + 多系统集成**（代码库、数据库、记忆、可观测），强调与真实系统交互的 agentic 能力；OpenAI Plugins/GPTs 提供「能力描述 + 调用契约」的插件模型。
- **小趣现状**：ReAct 在端侧已较完整，双门禁与领域路由与规格一致；**不足**在于流式仅「完成后回放 trace」，无逐 token/chunk 的 true streaming，且多轮 ReAct 对用户不可见（无「正在调用 XX 工具」的轻量暴露）。
- **借鉴点**：保持端侧 ReAct 作为回退与离线路径；在主路径（云/OpenClaw）上要求/实现逐 chunk 流式与步骤可视化；可选在 UI 层增加「本轮用了哪些工具/技能」的轻量可解释。

### 3.2 插件化与工具扩展

**当前实现**：

- **工具注册**：`AssistantToolRegistry` 为内存 Map，在 `AssistantRuntime._create()` 中一次性 `register(WebSearchTool())`、`UnifiedRetrievalTool`、`LocalContextTool`、`MediaGalleryTool`、`IntentBridgeTool`；无运行时从配置或远程拉取工具清单的机制。
- **插件化程度**：工具实现为 Dart 类，实现 `AssistantTool` 接口（`name`、`execute`）；**无**独立插件包、无签名/沙箱、无「按渠道或策略动态挂载工具」的 SPI。能力扩展依赖发版或配置绑死工具列表。
- **Adapter SPI**：渠道层有 `AssistentAdapterSpi`（verify/ingest/dispatch）、`AssistentAdapterRegistry`、`AssistentAdapterRuntime`；已实现 `AssistentOpenclawAdapter`、`AssistentFeishuAdapter`，将外部请求转为 `AssistentChannelEvent` 并交网关执行，结果经 `dispatch` 回写渠道。此为**渠道维度的插件化**，与「工具/Skill 插件」分离。

**OpenClaw 集成视角**：

- OpenClaw 通过 `GET /v1/skills` 同步技能元数据，再通过 `POST /v1/skills/invoke` 按 skill 调用；小趣侧技能由 Manifest + SkillExecutor 执行，内部会用到上述工具链，但**技能本身**目前为打包的 4 个 .skill.yaml，无第三方或远程注册技能。

**世界级参照与差距**：

- **Google ADK**：通过 Integrations 生态接入 GitHub、Notion、MongoDB、Pinecone 等，**能力以集成包形式扩展**，agent 与外部系统解耦。
- **OpenAI Plugins / GPTs**：开放「manifest + API 描述」，开发者自建后端即可扩展能力；平台不拥有工具实现，只做发现与调用契约。
- **小趣**：工具与技能均为「内置 + 配置」，无开放插件市场、无第三方 manifest 注册、无工具级权限与沙箱。**借鉴点**：短期保持内置工具与 19 垂类模板；中期可定义「Skill 描述契约 + 远程 invoke 端点」，允许合作方以「远程 Skill」形式接入；长期可考虑工具/Skill 的签名、审核与按渠道/租户的可见性策略。

### 3.3 Skill 体系与渠道维度

**Skill 定义与发现**：

- **Manifest**：id、name、description、version、executionTarget（ios_intent / android_intent / native_api / tool_chain）、parametersSchema、permissions、**channelScopes**（如 app、feishu、openclaw）、deviceScopes、tier、defaultEnabled；与 OpenClaw 能力迁移审计中的「技能市场治理：tier/channel/device/订阅策略」一致。
- **加载**：`PersonalAssistantSkillLoader.loadBundledSkills()` 从资产目录读 .skill.yaml；`SkillMarketService` 合并本地启用状态（SkillSubscriptionStore），提供 `listSkills()` / `listSkillsByChannel(channel)`；**无**从云侧拉取技能目录或同步授权状态的默认路径（契约有，端未贯通）。
- **执行**：`AssistantGateway.invokeSkill(skillId, arguments, deviceProfile)` → `SkillExecutor`；knowledge_qa / web.quick_search 走 KnowledgeQaEngine，其余走 tool-chain 步骤表；可配置 `remoteInvoker` 将某步交给远端（如 OpenClaw）。

**渠道（Channel）**：

- **语义**：`channel` 表示请求来源或目标展示端，如 `app`、`feishu`、`openclaw`；用于技能过滤（`channelScopes`）、审计与限流（如 `latencySensitive: channel != 'app'`）。
- **接入方式**：  
  - **App**：直接调 `CapabilityGateway` / `AssistantGateway`，channel=app。  
  - **OpenClaw**：通过 OpenClawBridge 调小趣 `runRemote` 或小趣 HTTP 网关；OpenClaw 也可拉取 skills 并 invoke，channel 传 openclaw。  
  - **Feishu**：通过 `POST /v1/assistent/channels/feishu` 等入口，由 `AssistentFeishuAdapter` ingest → 网关 run/invoke → dispatch 回飞书。
- **统一网关**：`openclaw_feishu_integration.md` 所列端点（/v1/skills、/v1/skills/invoke、/v1/run、/v1/run/stream、/v1/assistent/channels/{adapterId}）支持多渠道共用同一套 run/skill 能力，并可通过 token、签名策略（ASSISTENT_FEISHU_SIGN_MODE、ASSISTENT_OPENCLAW_SIGN_SECRET）做渠道级鉴权。

**差距与借鉴**：

- **世界级**：Alexa Skills、Google Actions 均提供**技能商店 + 分类 + 授权**，用户可见「能做什么」并管理授权；对话中可显式「打开 XX 技能」或由系统推荐技能。
- **小趣**：技能在 UI 上仅 4 个打包技能，与 19 垂类能力不统一；渠道维度有 channelScopes 与 Adapter SPI，但**技能发现与授权**未在端侧完整落地，suggested-actions 未与技能/场景强绑定。**借鉴点**：技能中心展示「领域技能/场景包」与 19 垂类一致；端侧对接云侧 skills 与 consent 接口；对话内增加「本次使用 XX 领域/技能」的轻量说明与推荐入口。

### 3.4 世界级水准四维对比（产品定位、架构技术、开放性、体验）

| 维度 | 世界级参照（Google ADK / Alexa / OpenAI 生态） | 当前小趣 | 差距摘要 | 借鉴点 |
|------|-----------------------------------------------|----------|----------|--------|
| **产品定位** | 通用助手 + 开放技能生态；B 端与 C 端并存 | 兴趣社交场景内的「找小趣」私人助理；C 位入口 | 定位清晰但能力边界偏「应用内」；缺少对外的「助理即平台」叙事 | 保持「兴趣 + 助理」差异化；可对外输出「小趣能力」为 OpenClaw/飞书等提供 run+skill，形成平台感 |
| **架构技术** | Agentic + 多系统集成；流式优先；集中可观测 | 端侧 ReAct + 双门禁 + 领域路由；远端优先可走 OpenClaw；工具内置 | 流式为「整段后回放」；多端/云侧 ReAct 未统一实现；可观测以端侧为主 | 主路径支持逐 chunk 流式；云侧 run/runStream 与端契约一致；trace/成本集中上报 |
| **开放性** | 第三方技能/插件注册、发现、授权、分成 | 渠道 Adapter SPI + 统一 HTTP 网关；Skill 为内置 + 打包，无第三方注册 | 渠道已开放，能力扩展仍闭源/内置 | 定义 Skill 开放契约（描述 + invoke 端点）；可选技能目录与 consent 对第三方可见 |
| **体验** | 首字快、步骤可见、错误分级、主动建议 | 整段展示、trace 可驱动中间态但未系统化；错误统一提示；suggested-actions 未充分用 | 首字与步骤感知弱；建议与场景/技能未打通 | 流式上屏、可解释折叠、错误分类、suggested-actions 与技能/页面绑定 |

### 3.5 小结与对后续章节的衔接

- **ReAct**：小趣端侧 ReAct 与 OpenClaw 能力审计结论一致，已具备多阶段与双门禁；主路径需补**真流式**与**步骤/工具可解释**。
- **插件化**：工具为内置注册，渠道为 Adapter SPI；可演进为「Skill/工具开放契约 + 远程注册或发现」，与世界级开放生态对齐。
- **Skill 与渠道**：Manifest、channelScopes、统一网关与 OpenClaw/Feishu 集成已就绪；**技能与 19 垂类统一呈现、授权与 suggested-actions 落地**为当前要补的体验与开放性缺口。
- 以下「对话交互」「技能管理」现状与「与 OpenClaw/世界级差距」「产品设计建议」与本节保持一致，并在此基础上细化落地项。

---

## 四、对话交互能力实现现状

### 4.1 架构概览

- **端侧**：`ChatDetailPage` 在 `conversationId == assistantConversationId` 时走助理分支；输入 → `CapabilityGateway.runStream()` → 消费 `AssistantRunStreamEvent`（trace / completed / failed）→ 展示最终回复并写回 `_messages`。
- **能力路由**：`CapabilityGateway` 支持 `remotePreferred`（商用默认）、`localOnly`、`hybrid`。`remotePreferred` 下先调 OpenClaw 远端，满足 `_isRemoteResponseCommercialReady()` 则用远端结果，否则回退本地 AgentLoop。
- **本地引擎**：`AssistantRuntime` → `PersonalAssistantAgentLoop`（ReAct++）→ `ReactRuntime` + `SwitchableAssistantLlmProvider`，工具链含 WebSearch、UnifiedRetrieval、LocalContext、MediaGallery、IntentBridge 等。
- **远端**：`OpenClawBridge.runRemote()` POST `baseUrl/v1/run`，请求体含 messages、sessionId、contextScopeHint、privacyPolicy 等；响应解析为 `AssistantRunResponse`，含 `finalText`、`structuredResponse`、`traces`。

### 4.2 已具备能力

- **会话延续**：历史消息以 `AssistantRunMessage` 形式传入，支持多轮对话。
- **上下文注入**：`_buildAssistantContextScope()` 从 `AssistantOpenContext`、当前页面类型、最近对话状态等组装 `contextScopeHint`，含 `pageType`、`userTags`、`privacyPolicy`、`dialogueState` 等。
- **领域路由**：先 `classifyDomain(query, contextScope)` 得到 `domainId`，再带入 request；端侧有 `domain_routing_catalog`（约 17 个主垂类 + fallback），与规格中「19 垂类」方向一致。
- **流式与轨迹**：`runStream` 可下发 trace 事件；`_consumeAssistantTraceEvent` 可驱动「思考中/检索中」等中间态（如 `_assistantSearchingCount`、`_assistantReferenceCount`）。
- **学习闭环**：成功后调 `AssistentLearningService.recordInteraction()`，写入 runId、traceId、query、answer、duration 等，支持后续画像与策略迭代。
- **回复展示**：优先取 `structuredResponse.uiAnswer.markdownText`，其次 `answerPayload.userFacingMarkdown`，再解析 JSON 或 raw，保证有可读兜底。

### 4.3 缺口与风险

- **流式逐字/逐句输出**：当前是「整段完成后一次性展示」，没有真正的 SSE 逐 chunk 上屏，与 Google Assistant / ChatGPT 的「边生成边看」体验有差距。
- **多模态输入**：以文本为主；语音入口、图片/卡片理解在规格或工具有提及，但端到端体验未在本次代码中突出。
- **错误与降级**：失败时统一展示 `assistantUnavailable`，没有按错误类型（网络/权限/限流/内容安全）做差异化提示与引导。
- **对话内快捷操作**：`uiActions` / `uiReferences` 已有结构，但 UI 上对「可点击的下一步建议」「引用来源」的暴露不够系统化，未形成强引导。

---

## 五、技能管理能力实现现状

### 5.1 技能定义与发现

- **Manifest**：`PersonalAssistantSkillManifest` 含 id、name、description、version、executionTarget（ios_intent / android_intent / native_api / tool_chain）、parametersSchema、permissions、channelScopes、deviceScopes、tier、defaultEnabled 等。
- **资产**：当前仅有 **4 个 .skill.yaml**：`knowledge_qa`、`reminder.intent`、`web.quick_search`、`photo.organize`；与规格中「19 垂类」「Skill 列表与授权」的规模有差距——垂类能力更多在「领域模板 + 工具链」中实现，而非独立 Skill 清单。
- **加载与市场**：`SkillMarketService` + `PersonalAssistantSkillLoader` 从资产加载；`AssistantGateway.listSkills()` / `listSkillsByChannel()` 供 UI 使用；`setSkillEnabled(skillId, enabled)` 支持开关。

### 5.2 技能中心 UI

- **AssistantSkillCenterPage**（`lib/ui/assistant/pages/assistant_skill_center_page.dart`）：展示技能列表、开关、订阅/策略卡、风险策略（低/中/高风险的自动运行/需确认/双确认）、场景闸门（discovery/circle/chat/system）、最近会话等。技能来源为 `assistantSkillMarketProvider`。
- **会话页内**：`_availableSkillNames` 从 `listSkills()` 过滤 enabled，用于展示或引导，但未在引用中看到强依赖「按技能选能力」的交互。

### 5.3 云侧契约

- **assistant-service**（`contracts/metadata/assistant/assistant_run/service.yaml`）：提供 runs、runs/stream、page-context、suggested-actions、learning/events、learning/scorecards、policy、**skills 列表**、**skills/{id}/consent 授权与撤销**。即：技能列表与授权在契约层已定义，端侧若对接云侧，可统一从 API 拉取并同步授权状态。

### 5.4 缺口与风险

- **端侧 Skill 与垂类能力脱节**：实际执行依赖「领域路由 + 模板 + 工具」，而「技能」在 UI 层更多是 4 个打包技能；用户感知的「能做什么」与「技能中心里看到的」不一致，易造成认知割裂。
- **授权与隐私**：契约有 consent 接口，端侧技能中心未明显看到「授权/撤销授权」的完整流程与说明文案。
- **技能发现与推荐**：缺少「根据当前页面/任务推荐技能」的主动推荐（suggested-actions 在 API 层存在，端侧利用不足）。
- **技能与对话的联动**：对话中「用哪个技能」对用户不透明；没有「建议使用 XX 技能」或「本次使用了 XX 技能」的轻量说明。

---

## 六、与 OpenClaw / Google Assistant 的差距（世界水准对标）

本节与 **§三（ReAct 框架、插件化、Skill 与渠道接入详析及世界级对标）** 中的四维对比表一致，此处按对话、技能、体验与**开放性**分项收束。

### 6.1 对话与理解

| 能力 | 当前小趣 | OpenClaw / Google Assistant 级 |
|------|----------|--------------------------------|
| 流式输出 | 整段完成后展示 | 逐 token/chunk 流式上屏 |
| 多轮与上下文 | 有 session + 历史消息 | 长期记忆 + 跨会话偏好 + 实体解析 |
| 多模态 | 文本为主 | 语音 in/out、图像/文档理解、富媒体卡片 |
| 领域覆盖 | 17 垂类 + fallback | 开放域 + 深度垂类 + 可扩展技能生态 |
| 错误与降级 | 统一「不可用」 | 分类型提示、重试、降级到本地/缓存 |

### 6.2 技能与生态

| 能力 | 当前小趣 | 世界水准 |
|------|----------|----------|
| 技能数量与分类 | 4 个打包技能 + 模板垂类 | 大量官方 + 第三方技能，分类与发现完善 |
| 技能授权与隐私 | API 有 consent，端侧未贯通 | 明确授权流、权限说明、可撤销 |
| 技能与对话融合 | 路由在后台，用户不可见 | 对话中可显式调用/推荐技能，结果可溯源 |
| 建议与主动 | suggested-actions 未充分用 | 场景化建议、快捷短语、主动提醒 |

### 6.3 体验与可观测

| 能力 | 当前小趣 | 世界水准 |
|------|----------|----------|
| 首字延迟 / 响应感知 | 依赖进度动画与 trace | 流式首字快 + 进度/步骤可视化 |
| 可解释性 | trace 有，UI 未系统展示 | 「用了什么数据/技能」可展开查看 |
| 个性化 | 有 learning 上报与画像规格 | 越用越准的偏好、习惯与主动服务 |

### 6.4 开放性（平台与生态）

| 能力 | 当前小趣 | 世界水准 |
|------|----------|----------|
| 渠道开放 | Adapter SPI + 统一 HTTP 网关；OpenClaw/Feishu 可调 run、skills、invoke | 多端/多入口统一 API，第三方可集成 |
| 技能/插件开放 | Skill 为内置 + 打包 .skill.yaml；无第三方注册、无技能商店 | 第三方可注册技能、审核、授权、分成（如 Alexa Skills、OpenAI GPTs） |
| 可观测与成本 | runId/traceId 贯通；商业网关有审计与 CostLedger；端侧为主 | 全链路可观测、成本与用量可按渠道/租户统计与计费 |
| 契约与文档 | 集成文档与契约（openclaw_feishu_integration、assistent_adapter_spi）清晰 | 公开 API 文档、SDK、示例与最佳实践 |

**借鉴点**：在保持「兴趣 + 助理」产品差异的前提下，将小趣能力对外输出为「run + skills」平台（已部分通过 OpenClaw/Feishu 实现）；中长期可定义 Skill 开放契约（描述 + invoke 端点）、可选第三方技能目录与 consent 流程，向「助理即平台」演进。

---

## 七、产品设计与优化升级建议

### 7.1 战略与体验层（产品设计）

1. **明确「C 位」的承诺**
   - 在首屏/引导/空状态强化「找小趣 = 一件事就搞定」：问、办、记、发、找、排（规格中六类命令式动作）在 UI 上有清晰入口或示例。
   - 从「对话」升级为「任务 + 陪伴」双主线：任务型（查、办、订）与陪伴型（聊、读、推荐）在首句建议或快捷 chips 上区分。

2. **统一「找小趣」与三层形态**
   - 全站统一「找小趣」语义；C 位点击 = 进入会话并带当前页面 context。
   - 在发现/内容详情等场景强化「帮读卡」「任务抽屉」形态，减少「必须进全屏会话」的负担，与规格中「先半弹窗再可选完整对话」对齐。

3. **首屏与冷启动**
   - 小趣会话空状态：根据 `AssistantOpenContext` 与 pageType 展示「当前适合干啥」+ 推荐 chips，而非空白输入框。
   - 欢迎句与 chips 由配置驱动（如 assistant_prompt_config），与规格一致。

### 7.2 对话交互能力（设计与实现）

4. **流式输出与首字延迟**
   - 目标：支持 SSE/stream 逐 chunk 推送，端侧逐字或逐句追加到当前气泡，并保留「思考中/检索中」的中间态。
   - 需云侧/OpenClaw 提供 stream 接口与 chunk 格式；端侧 `runStream` 增加 `chunk` 事件类型并更新 UI。

5. **错误与降级体验**
   - 按错误码/类型展示：网络不可用（含重试）、权限未授权（引导去设置）、限流（稍后重试）、内容安全（换说法）等，文案走 l10n 与 errors 契约。
   - 远端不可用时明确提示「当前使用本地能力」，避免用户误以为「坏了」。

6. **对话内结构化与下一步**
   - 系统化渲染 `uiAnswer`、`uiActions`、`uiReferences`：可点击的「下一步」按钮、引用来源折叠/展开、时间线式步骤（uiTimeline）。
   - 让「结论 + 依据 + 下一步」成为默认呈现形态，而非纯一段 markdown。

7. **多模态与语音（中期）**
   - 语音输入/输出与现有输入框并存；图片/文档上传与「帮读」结合。
   - 与设备能力（IntentBridge、LocalContext）结合，形成「说一句/拍一张就能办」的体验。

### 7.3 技能管理能力（设计与实现）

8. **技能与垂类统一心智**
   - 将「用户可见能力」统一为「技能」：19 垂类在技能中心以「领域技能」或「场景包」形式展示（如天气、出行、知识问答、情感陪伴等），与后端 domain 路由一致。
   - 每个技能：名称、一句话描述、示例问句、开关、如需则授权；避免「只有 4 个技能」与「实际能聊很多」的割裂。

9. **授权与隐私贯通**
   - 端侧技能中心对接 `GET/POST/DELETE .../skills` 与 `.../skills/{id}/consent`，展示授权状态与「授权/撤销」操作。
   - 首次使用需权限的技能时，在对话流中触发授权引导（与规格中「最小必要上下文」「逐步披露」一致）。

10. **场景化建议与主动能力**
    - 在会话空状态或关键节点调用 `suggested-actions`（含 pageType、objectId），展示「根据当前页面推荐的操作」。
    - 在发现/圈子等页的「找小趣」入口预填或推荐与当前内容相关的问法（如「总结这篇」「推荐类似」）。

11. **开放性与插件化（与 §3 对齐）**
    - **渠道**：保持并完善 Adapter SPI 与统一网关（/v1/run、/v1/skills、/v1/assistent/channels/{adapterId}），文档化 OpenClaw/Feishu 等接入方式。
    - **Skill 开放契约**：定义「Skill 描述 + invoke 端点」契约，便于合作方以远程 Skill 形式接入；可选支持从云侧拉取技能目录与授权状态。
    - **可观测**：runId/traceId 与成本按 channel 上报，支持按渠道/租户的用量与质量分析。

### 7.4 技术与可观测

12. **可解释与信任**
    - 在助理回复下方提供「本次用了哪些能力/来源」（如检索、某技能、某领域），可折叠，满足「可解释」与合规需求。
    - 将 trace 中的关键步骤以轻量时间线形式可选展示（不打扰主阅读）。

13. **性能与 SLO**
    - 定义并监控首字延迟、端到端响应时间、错误率；远端/本地回退比例与原因打点，驱动优化与容量规划。
    - 规格中已有质量门禁与回滚阈值，需在端侧有对应观测与告警。

### 7.5 优先级建议（落地顺序）

| 优先级 | 建议项 | 说明 |
|--------|--------|------|
| P0 | 流式输出 + 首字延迟优化 | 对话体验最直观，直接影响「世界水准」感知 |
| P0 | 错误与降级文案/引导 | 提升可用性与信任，工作量相对可控 |
| P1 | 对话内 uiActions/uiReferences 系统化展示 | 强化「可执行建议」与依据可见 |
| P1 | 技能与垂类统一 + 技能中心展示 19 领域 | 解决「能做什么」与「看到什么」一致 |
| P1 | suggested-actions 与空状态 chips 落地 | 降低冷启动摩擦，提高「找小趣」价值 |
| P2 | 授权/consent 端到端 + 隐私说明 | 合规与用户控制感 |
| P2 | 多模态（语音/图片）与「帮读」深化 | 差异化与场景深度 |
| P2 | 可解释性 UI（来源/步骤折叠） | 信任与调试 |

---

## 八、小结

- **战略**：将小趣放在底部导航 C 位，已清晰表达「全面升级私人助理」的产品转型；关键是让对话与技能体验支撑「有事就找小趣」的心智。
- **ReAct 与端云分工**：端侧 ReAct++ 与双门禁已与 OpenClaw 能力审计对齐；主路径可走 OpenClaw 全量 run，回退走端侧；详见 **§二、§三**。
- **框架、插件化、Skill、渠道**：**§三** 已详述 ReAct 链路、工具/Adapter 插件化程度、Skill 与 channelScopes、以及与世界级（Google ADK、Alexa、OpenAI 生态）在**产品定位、架构技术、开放性、体验**四维的对比与借鉴点；渠道已通过 Adapter SPI 与统一网关开放，Skill/工具侧可向「开放契约 + 可选第三方注册」演进。
- **对话**：已有领域路由、上下文、学习闭环与双门禁规格；需补流式输出、错误分级、对话内结构化与多模态，以逼近世界级体验。
- **技能与开放性**：契约与模板体系完善；端侧技能与 19 垂类需统一呈现，授权与 suggested-actions 需落地；开放性上可对外输出「run + skills」平台并逐步定义 Skill 开放契约。

按上述 P0/P1/P2 分阶段落地，可逐步将小趣打造成「世界水准级」的私人助理入口，并与现有兴趣内容、圈子、趣聊形成清晰协同关系。
