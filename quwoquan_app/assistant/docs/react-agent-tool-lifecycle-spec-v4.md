# ReAct + Agent + 工具生命周期 设计规格 v4

> **版本**：v4.0 · **日期**：2026-03-07（从 v3 升级）
> **主要变更**：LLM-first Skill 路由 · OpenClaw 安全守卫层 · 9 工具体系 · Memory Auto-recall · 学习闭环
> **架构总览**：参见 [architecture_overview.md](architecture_overview.md)
>
> **收口说明**：当前主入口为 `PERSONAL_ASSISTANT_ARCHITECTURE_AND_FLOW.md`。本文档保留为 ReAct 生命周期与工具链详细规格参考。

---

## 一、架构分层

```
用户消息 → AssistantEntry → AssistantAgentLoop → ReactRuntime(ReAct循环) → Synthesizer
                ↓                  ↓                      ↓                    ↓
         ContextOrchestrator  SkillCatalog          ToolRegistry          StreamingSynthesis
         Memory Auto-recall   domain_router         ExecutionGuard        LearningFeedback
                              (catalog only)        LoopDetector
                                                    ResultTruncator
```

### 1.1 分层职责

| 层 | 组件 | 职责 |
|---|---|---|
| 编排层 | `AssistantAgentLoop` + `LocalPhaseExecutionOwner` | 请求预处理、记忆召回、Skill 加载、上下文装配、合成就绪门禁、学习存储 |
| 规划层 | `LLM Planner` | 自主选择 primaryDomainId + mode + inferredMotive + queryVariants |
| 执行层 | `ReactRuntime` | ReAct 循环核心（Reason → Act → Observe → Assess → Decide） |
| 安全层 | `ToolExecutionGuard` | 循环检测 + 权限检查，前置拦截 |
| 工具层 | `ToolRegistry` + 9 个工具 | 工具注册、执行、结果截断 |
| 模型层 | `SwitchableAssistantLlmProvider` | 模型调用、SSE streaming、降级重试 |
| 事件层 | `LocalAssistantEntry` / `RemoteAssistantEntry` | 内部 trace → 用户阶段事件翻译 |
| UI 层 | `ChatDetailPage` | 阶段 timeline、流式思考气泡、答案渲染 |

### 1.2 核心设计原则

1. **LLM 自主决策**：意图识别、Skill 选择、搜索策略全部由 LLM 判断，引擎不做规则路由
2. **安全兜底**：三层守卫（循环检测 → 结果截断 → 权限检查）在 LLM 决策之外保障稳定性
3. **元数据驱动扩展**：新增 Skill 只需声明 description/mode，新增工具只需注册元数据
4. **用户语言唯一出口**：所有面向用户的文案由元数据翻译层产生，禁止暴露内部字符串
5. **Memory-first**：记忆在 ReAct 前自动召回，无需 LLM 主动调用 memory_search

---

## 二、LLM-first Skill 路由（v4 新增）

### 2.1 设计原因

v3 使用 `intentKeywords` 子串匹配路由（`domain_router.classify()`）。问题：
- 关键词覆盖不全（"帮我看看明天出行"不含"天气"关键词）
- 无法处理语义/跨域
- 需要持续维护关键词列表

v4 方案：**完全移除关键词路由，由 Planner LLM 看到所有 Skill 描述后自主选择**。

### 2.2 Skill 描述注入

`domain_router.dart` 的 `buildSkillCatalogPrompt()` 生成如下文本注入 planner：

```
- weather: 天气查询、出行建议、穿衣推荐、空气质量。可设出行提醒。 [mode=hybrid]
- finance_consumer: 理财分析、基金/股票/保险对比、投资建议、贷款预算规划。 [mode=qa]
- calendar_task: 日程管理、提醒设置、待办跟踪、会议安排。 [mode=task]
...（共 15 行）
```

总计约 600 字符，几乎不占 context 预算。

### 2.3 Planner LLM 输出格式

```json
{
  "primaryDomainId": "finance_consumer",
  "mode": "qa",
  "inferredMotive": "在做投资研究，想找台积电供应链中的A股标的",
  "slotFillPlan": {
    "timeScope": { "value": "today", "detectedFrom": "default" }
  },
  "queryNormalization": {
    "normalizedQuery": "台积电供应商A股上市公司",
    "queryVariants": [
      "台积电 供应商 A股 上市公司",
      "台积电供应链 A股投资标的 2025",
      "台积电供应商名单 site:eastmoney.com"
    ]
  }
}
```

### 2.4 代码映射

```
AssistantAgentLoop._buildTemplateVariables()
  └─ _domainRouter.buildSkillCatalogPrompt() → {{skillCatalog}}
  
AssistantAgentLoop.classifyDomain()
  └─ 直接返回 fallbackDomainId（不做关键词匹配）
  └─ 真实 domainId 由 planner LLM 输出后从 _plannerOutputCache 提取
```

---

## 三、ReAct 循环完整规格

### 3.1 主循环伪代码（v4 版本）

```
function ReactRuntime.run(messages, goal, tools, onTraceEvent):
  state = ReactRunState(goal, maxIterations, toolBudget)
  
  emit(lifecycleStart)
  
  while !state.shouldStop:
    state.iteration++
    
    // ── Phase: Reason ──
    emit(thinkingStarted, iteration)
    output = llmProvider.reason(messages, tools, onDelta: emit(thinkingProgress))
    emit(assistantDelta, output.text, output.toolCalls)
    
    // ── 空输出安全阀 ──
    if output.isEmpty && noToolCalls:
      state.consecutiveEmptyIterations++
      if >= 2: stopReason = 'consecutive_empty'; break
    
    // ── 直接回答 ──
    if noToolCalls:
      finalText = output.text
      stopReason = 'model_answered_directly'
      break
    
    // ── Phase: Act ──
    plan = buildPlan(output.toolCalls)
    addAssistantToolCallMessage(messages, output.toolCalls)
    
    for step in plan:
      // ── 预算检查 ──
      if state.shouldStopByBudget:
        stopReason = 'tool_budget_exhausted'
        break
      
      // ── [NEW v4] 安全守卫 Pre-execution check ──
      guardResult = executionGuard.checkBeforeExecution(step.toolName, step.arguments)
      
      if guardResult.isBlocked:
        emit(toolError, guardResult.reason)
        stopReason = 'guard_blocked'
        break
      
      if guardResult.needsConfirmation:
        emit(toolStart, needsConfirmation=true, toolName, args)
        // UI 展示确认卡片，等待用户确认（异步）
      
      // ── Phase: Observe（执行工具）──
      emit(toolStart, step.toolName)
      result = toolRegistry.execute(step.toolName, step.arguments)
      
      // ── [NEW v4] 结果截断 ──
      truncatedObservation = resultTruncator.truncate(result.content)
      
      // ── [NEW v4] 更新循环检测器（加入结果哈希）──
      executionGuard.recordResult(step.toolName, step.arguments, truncatedObservation)
      
      addToolResultMessage(messages, step.toolCallId, truncatedObservation)
      emit(toolCompleted, step.toolName, result.data)
      
      // ── Phase: Assess（收敛判定）──
      assessment = toolResultAssessor.assess(step, result, state, skillPolicy)
      
      switch assessment.type:
        case sufficient:
          // 信息充分，继续或退出
        case needMoreSearch:
          if _consecutiveLowQuality >= 2:
            // 强制收敛，基于已有信息成答
            stopReason = 'consecutive_low_quality'
            break
          injectReflectionPrompt(messages, result)  // 下一轮扩大搜索
        case toolFailed:
          injectDegradedPrompt(messages)
        case budgetExhausted:
          break
    // end for
  // end while
  
  emit(lifecycleEnd, stopReason)
  return ReactRuntimeResult(finalText, traces)
```

### 3.2 阶段判定规则（保持 v3 不变）

```dart
String _determineUserPhase(ReactRunState state) {
  if (state.iteration == 1 && state.evidences.isEmpty) return 'understanding';
  if (state.evidences.isNotEmpty) return 'analyzing';
  return 'understanding';
}
```

---

## 四、三层安全守卫（v4 新增）

### 4.1 ToolLoopDetector

检测重复/无进展的工具调用，防止无限循环消耗 token。

```dart
class ToolLoopDetector {
  static const _historySize = 20;        // 全局断路器上限
  static const _criticalRepeatCount = 6; // 同参数重复调用阈值

  LoopResult check(toolName, args, resultHash?) {
    argsHash = _hash(toolName, args)
    
    // 1. 重复调用检测（相同 toolName + 相同参数）
    repeats = history.where(c => c.argsHash == argsHash).length
    if repeats >= _criticalRepeatCount:
      return LoopResult.blocked('$toolName 相同参数已调用 $repeats 次')
    
    // 2. 无进展检测（返回相同结果）
    sameResults = history.where(c => c.argsHash == argsHash && c.resultHash == resultHash)
    if sameResults >= 3:
      return LoopResult.blocked('$toolName 连续返回相同结果')
    
    // 3. 全局断路器
    if history.length >= _historySize:
      return LoopResult.blocked('工具调用总数达上限')
    
    history.addLast(_CallRecord(argsHash, resultHash))
    return LoopResult.ok()
  }
}
```

### 4.2 ToolResultTruncator

防止大体积工具结果（如长网页）撑满 context window。

```dart
class ToolResultTruncator {
  final contextWindowChars = 60000;   // 移动端保守估计
  final maxContextShareRatio = 0.3;   // 单工具结果最多占 30%
  final hardMaxChars = 200000;
  final minKeepChars = 1500;

  String truncate(String result) {
    maxChars = min(contextWindowChars * maxContextShareRatio, hardMaxChars)
    if result.length <= maxChars: return result
    
    keepChars = max(maxChars - 80, minKeepChars)
    cutPoint = result.lastIndexOf('\n', keepChars)
    effectiveCut = (cutPoint > keepChars * 0.8) ? cutPoint : keepChars
    return result[0..effectiveCut] + '\n\n[内容已截断，原始 ${result.length} 字符]'
  }
}
```

### 4.3 ToolExecutionGuard

前置统一拦截点：在工具执行之前先过循环检测 + 权限检查。

```dart
class ToolExecutionGuard {
  GuardResult checkBeforeExecution(toolName, args) {
    // 1. 循环检测
    loopResult = loopDetector.check(toolName, args, null)
    if loopResult.blocked: return GuardResult.blocked(loopResult.reason)
    
    // 2. 权限检查（scheduler/app_action/intent_bridge 需用户确认）
    perm = permissions[toolName]
    if perm?.requireConfirmation: return GuardResult.needsConfirmation(toolName, args)
    
    return GuardResult.allowed()
  }
}
```

**敏感工具权限配置**（`tool_permissions.json`）：

| 工具 | requireConfirmation | 说明 |
|---|---|---|
| `scheduler` | true | 创建/修改日历需用户确认 |
| `app_action` | true | 打电话/发短信等不可逆操作 |
| `intent_bridge` | true | 系统 Intent 跳转 |
| `deep_link` | false | 仅跳转，可自动执行 |
| 其他 | false | 查询类工具无需确认 |

---

## 五、Memory Auto-recall（v4 新增）

### 5.1 设计原因

v3 需要 LLM 主动决定调用 `memory_search` 才能使用历史记忆，导致遗忘率高。
v4 在 `AssistantAgentLoop` 进入 ReAct 之前自动执行召回，LLM 无需感知接口。

### 5.2 执行时机

```
AssistantAgentLoop.run(request)
  ├─ _assembleContext()                      ← 会话历史摘要
  ├─ recallByText(query, limit=3)            ← [AUTO-RECALL] ReAct 前自动执行
  │   └─ 结果注入 <memory_recall> 块到 messages
  └─ _runtime.run(messages, ...)             ← 进入 ReAct 循环
```

### 5.3 学习闭环（v4 新增）

每轮结束后，从 LLM 输出的 `learningSignals.profileTagDelta` 提取画像标签并持久化：

```dart
// local_phase_execution_owner._persistLearningTags()
tags = response.structuredResponse['learningTrack']['profileTagDelta']
// 格式: [{tag: 'city', value: '深圳'}, {tag: 'interest', value: '科技股'}]

await memoryRepository.rememberText(
  id: 'learning_${sessionId}_${timestamp}',
  text: '用户画像标签: ${tagSummary}',  // 自然语言格式，可被 recall
  metadata: {type: 'learning_tag', tags: tags}
)
```

下轮对话的 auto-recall 会自动捞取这些标签，形成画像闭环。

---

## 六、9 工具生命周期

### 6.1 工具注册（AssistantRuntime._create()）

```dart
final toolRegistry = AssistantToolRegistry()
  ..register(WebSearchTool())          // queryVariants 并发搜索
  ..register(WebFetchTool())           // 网页正文抓取
  ..register(MemorySearchTool())       // 向量语义记忆检索
  ..register(LocalContextTool())       // GPS + 设备上下文
  ..register(MediaGalleryTool())       // 相册访问
  ..register(IntentBridgeTool())       // iOS AppIntent / Android Intent
  ..register(SchedulerTool())          // [NEW v4] 日历 CRUD
  ..register(DeepLinkTool())           // [NEW v4] 内/外链接跳转
  ..register(AppActionTool());         // [NEW v4] 打电话/短信/导航/剪贴板
```

### 6.2 工具执行 Hook 链

```
before_tool_call:
  1. ToolExecutionGuard.checkBeforeExecution()  ← 循环检测 + 权限检查
  2. emit(toolStart, metadata.startLabel)

execute:
  3. toolRegistry.execute(toolName, arguments)

after_tool_call:
  4. ToolResultTruncator.truncate(result)       ← 截断大结果
  5. ToolExecutionGuard.recordResult()           ← 更新结果哈希
  6. addToolResultMessage(messages, observation)
  7. emit(toolCompleted, metadata.completedTemplate)
  8. ToolResultAssessor.assess()                 ← 收敛判定
```

### 6.3 web_search 多路并发

Planner LLM 在 `queryNormalization.queryVariants` 中生成 3 条差异化搜索词：

```dart
// websearch_tool._executeMultiQuery()
final results = await Future.wait(
  allQueries.map((q) => _searchWithProvider(query: q, config: config))
);
// 合并结果，按相关性去重
```

---

## 七、合成阶段

### 7.1 合成就绪判定（Phase Owner）

`LocalPhaseExecutionOwner._assessSynthesisReadiness()` 在 ReactRuntime 返回后判断是否有足够信息成答：

- `sufficient`：直接调用 `synthesizer.final_answer.md`
- `insufficient`：降级，基于已有部分信息生成答案 + 注明不确定性
- `degraded`：直接返回降级回复

### 7.2 多技能融合（跨域时）

当 planner 输出 `secondaryDomains` 时，phase owner 并发启动子代理，各自完成后由 `synthesizer.multi_skill_fusion.md` 融合：

```
主 AssistantAgentLoop
  ├─ 主技能 subagent (primaryDomainId)
  ├─ 副技能 subagent_1 (secondaryDomains[0])
  └─ 副技能 subagent_2 (secondaryDomains[1])
              ↓
  synthesizer.multi_skill_fusion.md
  ── 结论先行 ── 分域分节 ── 来源透明 ──
```

---

## 八、v3 → v4 变更对比

| 能力 | v3 | v4 |
|---|---|---|
| 意图路由 | `intentKeywords` 关键词子串匹配 | LLM 读 skillCatalog 自主选择 |
| 循环检测 | `consecutiveEmptyIterations >= 2` | ToolLoopDetector（20步历史 + 结果哈希）|
| 工具结果大小 | 无限制 | ToolResultTruncator（30% context上限）|
| 工具权限 | 无 | ToolExecutionGuard + tool_permissions.json |
| 记忆召回 | LLM 主动调 memory_search | ReAct 前自动 auto-recall |
| 工具数量 | 6 | 9（+scheduler, deep_link, app_action）|
| 搜索策略 | 单路查询 | queryVariants 三路并发 |
| 学习闭环 | 无 | `_persistLearningTags()` 每轮持久化 |

---

## 九、关键文件

| 文件 | 说明 |
|---|---|
| `lib/assistant/application/assistant_edge_service.dart` | 当前 edge assistant 公开创建入口 |
| `lib/assistant/runtime/assistant_runtime.dart` | 当前公开 runtime 封装 |
| `lib/assistant/application/local_assistant_entry.dart` | 当前本地执行入口 |
| `lib/assistant/application/remote_assistant_entry.dart` | 当前远程执行入口 |
| `lib/assistant/application/assistant_journey_projector.dart` | canonical 用户旅程投影入口 |
| `lib/assistant/spi/assistant_adapter_runtime.dart` | 当前渠道 Adapter SPI |
| `lib/assistant/tools/tool_schema.dart` | 当前工具合同入口 |
| `assets/assistant/prompts/global/planner.global_plan.md` | Planner 提示词 |
| `assets/assistant/tools/catalog/tool_permissions.json` | 工具权限配置 |

补充说明：更深层 ReAct / tool loop 细节当前仍通过 `lib/personal_assistant/` 兼容实现承接，但不再作为新增依赖入口。
