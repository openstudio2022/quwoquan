# ReAct + Agent + 工具生命周期 设计规格 v3

> 基于 OpenClaw 深度对标分析 + 业界一流方案，全面升级自主探索闭环。

---

## 一、架构总览

```
用户消息 → AgentLoop → ReactRuntime (ReAct循环) → LLM + Tools → 合成答案
                ↓                    ↓                              ↓
         ContextOrchestrator   ToolRegistry (Hook链)         StreamingSynthesis
                                     ↓
                              ToolMetadataRegistry → UI 阶段事件翻译 → 流式渲染
```

### 1.1 分层职责

| 层 | 组件 | 职责 |
|---|---|---|
| 编排层 | `AgentLoop` | 请求预处理、上下文装配、ReAct 调度、合成就绪门禁、gap fill |
| 执行层 | `ReactRuntime` | ReAct 循环核心（Reason → Act → Observe → Assess → Decide） |
| 工具层 | `ToolRegistry` + Hook 链 | 工具注册、参数校验、执行、循环检测、结果记录 |
| 模型层 | `LlmProvider` | 模型调用、SSE streaming、降级重试 |
| 事件层 | `CapabilityGateway` | 内部 trace → 用户阶段事件翻译 |
| 元数据层 | `ToolMetadataRegistry` | 工具 schema、用户交互语义、prompt hint |
| UI 层 | `ChatDetailPage` + `ChatMessageBubble` | 阶段 timeline、流式思考、答案渲染 |

### 1.2 核心设计原则

1. **LLM 自主决策 + 引擎安全兜底**：工具结果的下一步由 LLM 判断，引擎只做安全拦截（循环检测、预算耗尽、降级）
2. **元数据驱动扩展**：新增工具只需声明元数据，核心引擎和 UI 零改动
3. **用户语言唯一出口**：所有面向用户的文案由元数据和翻译层产生，禁止暴露内部字符串
4. **Hook 链式生命周期**：before_tool_call → execute → after_tool_call，每个阶段可插入逻辑

---

## 二、ReAct 循环完整规格

### 2.1 主循环伪代码

```
function ReactRuntime.run(messages, maxIterations, goal, tools, onTraceEvent):
  state = ReactRunState(goal, maxIterations, toolBudget=maxIterations*2)
  
  emit(lifecycleStart)
  emit(planStarted, goal)
  
  while !state.shouldStop:
    state.iteration++
    
    // ── Phase: Understanding / Analyzing ──
    currentPhase = determineUserPhase(state)
    phaseHint = buildPhaseHint(currentPhase, tools)
    injectSystemMessage(messages, phaseHint)
    
    emit(thinkingStarted, iteration, phase=currentPhase)
    
    output = llmProvider.reason(
      messages, tools,
      onDelta: (delta) => emit(thinkingProgress, delta, phase=currentPhase)
    )
    
    emit(assistantDelta, output.text, toolCalls)
    
    // ── 空输出安全阀 ──
    if output.isEmpty && noToolCalls:
      state.consecutiveEmptyIterations++
      if state.consecutiveEmptyIterations >= 2:
        state.stopReason = 'consecutive_empty_iterations'
        emit(loopDegraded, "遇到了一些困难，将基于已有信息为您回答")
        break
    else:
      state.consecutiveEmptyIterations = 0
    
    // ── 直接回答路径 ──
    if noToolCalls:
      finalText = output.text
      state.stopReason = 'model_answered_without_tools'
      if output.degraded:
        emit(loopDegraded, "服务暂时繁忙")
        return degradedResult
      break
    
    // ── Phase: Tool Execution ──
    plan = planner.buildPlan(toolCalls)
    addAssistantToolCallMessage(messages, toolCalls)
    
    for step in plan:
      if step.toolName.isEmpty:
        stopReason = 'plan_step_without_tool'
        break
      if state.shouldStopByBudget:
        stopReason = 'tool_budget_exhausted'
        emit(loopDegraded, "已收集到部分信息，开始组织回答")
        break
      
      // ── before_tool_call hook ──
      loopCheck = toolRegistry.checkLoop(state, step)
      if loopCheck.blocked:
        emit(loopDegraded, loopCheck.userMessage)
        break
      
      emit(toolExecutionStarted, step.toolName, metadata.startLabel)
      
      result = toolRegistry.execute(step.toolName, step.arguments)
      
      // ── after_tool_call hook ──
      toolRegistry.recordOutcome(state, step, result)
      
      observation = buildToolObservation(step.toolName, result)
      addToolResultMessage(messages, step.toolCallId, observation)
      
      if result.success:
        emit(toolExecutionCompleted, step.toolName, metadata.completedTemplate, result.data)
      else:
        emit(toolExecutionCompleted, step.toolName, status=failed)
      
      // ── Phase: Assessment（工具后闭环）──
      assessment = assessToolResult(step, result, state, policy)
      emit(toolAssessmentStarted)
      
      switch assessment.outcome:
        case sufficient:
          emit(toolAssessmentResult, sufficient, "信息充分")
          // 继续下一个 step 或进入下一轮
          
        case needReflection:
          emit(toolAssessmentResult, needMoreSearch, "信息不够全面，扩大搜索范围")
          injectReflectionPrompt(messages, result)
          // 不 break，让 LLM 在下一轮决定重写查询
          
        case needReplan:
          emit(toolAssessmentResult, needMoreSearch, "还需要更多信息")
          state.openQuestions.add('step ${step.id} needs re-check')
          break // → 回到 while 循环
          
        case toolFailed:
          if shouldSuppress(step.toolName, result):
            emit(toolAssessmentResult, toolFailed, "暂时无法使用，改用已有知识")
            injectDegradedPrompt(messages)
          else:
            emit(toolAssessmentResult, toolFailed, result.message)
            finalText = result.message
            
        case budgetExhausted:
          emit(loopDegraded, "已收集到部分信息，开始组织回答")
          break
    // ── end for ──
  // ── end while ──
  
  // ── 兜底处理 ──
  if finalText.isEmpty:
    finalText = extractLastDelta(traces) ?? '本次任务已完成，但没有生成可展示结果。'
  
  emit(lifecycleEnd, stopReason)
  return ReactRuntimeResult(finalText, traces)
```

### 2.2 阶段判定规则

```dart
String _determineUserPhase(ReactRunState state) {
  // 第 1 轮且无工具证据 → 理解阶段
  if (state.iteration == 1 && state.evidences.isEmpty) {
    return 'understanding';
  }
  // 有工具证据且当前迭代无新工具调用 → 分析阶段
  if (state.evidences.isNotEmpty) {
    return 'analyzing';
  }
  // 默认
  return 'understanding';
}
```

### 2.3 合成阶段（AgentLoop 层）

```
reactResult = runtime.run(...)

// ── 合成就绪门禁 ──
synthesisReady = contextOrchestrator.checkSynthesisReadiness(...)
if !synthesisReady:
  emit(toolAssessmentResult, needMoreSearch, gapFill=true, "关键信息不完整，补充获取中")
  retryResult = runtime.run(retryMessages, templateId='postcondition_check')
  emit(toolAssessmentResult, sufficient, "信息补齐完成")
  mergedResult = merge(reactResult, retryResult)

// ── SSE 流式合成 ──
emit(answeringStarted)
streamedText = runtime.streamSynthesis(
  messages, onDelta: (delta) => emit(answeringDelta, delta)
)
emit(answeringCompleted)
```

---

## 三、工具生命周期规格

### 3.1 Hook 链架构（借鉴 OpenClaw）

```
┌─────────────────────────────────────────────────────┐
│                 ToolRegistry.execute()                │
│  ┌──────────────────┐  ┌──────────┐  ┌────────────┐ │
│  │ before_tool_call │→│  execute  │→│after_tool_call│ │
│  │  ┌─循环检测─┐    │  │ (actual) │  │ ┌─结果记录─┐│ │
│  │  │ hash比对 │    │  │          │  │ │ hash存储 ││ │
│  │  │ 模式匹配 │    │  │          │  │ │ 进展检测 ││ │
│  │  └─────────┘    │  │          │  │ └─────────┘│ │
│  │  ┌─参数校验─┐    │  │          │  │ ┌─用户事件─┐│ │
│  │  │ required │    │  │          │  │ │ assessment│ │
│  │  │ type     │    │  │          │  │ │ outcome  ││ │
│  │  └─────────┘    │  │          │  │ └─────────┘│ │
│  │  ┌─用户事件─┐    │  │          │  │            │ │
│  │  │ toolStart│    │  │          │  │            │ │
│  │  └─────────┘    │  │          │  │            │ │
│  └──────────────────┘  └──────────┘  └────────────┘ │
└─────────────────────────────────────────────────────┘
```

### 3.2 ToolRegistry 改造

```dart
class AssistantToolRegistry {
  // 现有
  final Map<String, AssistantTool> _tools;
  final ToolMetadataRegistry? _metadataRegistry;
  
  // 新增：工具调用历史（用于循环检测）
  final ToolCallHistory _callHistory = ToolCallHistory();
  
  Future<AssistantToolResult> execute(
    String name,
    Map<String, dynamic> arguments, {
    ToolCallContext? context,  // 新增：传入 sessionState 等上下文
  }) async {
    // 1. before hook: 循环检测
    final loopCheck = _callHistory.detectLoop(name, arguments);
    if (loopCheck.blocked) {
      return AssistantToolResult(
        success: false,
        message: loopCheck.reason,
        errorCode: AssistantErrorCode.loopDetected,
      );
    }
    _callHistory.recordCall(name, arguments);
    
    // 2. 参数校验（现有逻辑）
    final argCheck = _validateArguments(name: name, arguments: arguments);
    if (argCheck != null) return argCheck;
    
    // 3. 执行
    try {
      final result = await tool.execute(arguments);
      // 4. after hook: 记录结果用于循环检测
      _callHistory.recordOutcome(name, arguments, result);
      // 5. 输出校验
      return _validateOutput(name: name, result: result) ?? result;
    } catch (error) {
      _callHistory.recordOutcome(name, arguments, null, error: error);
      return AssistantToolResult(
        success: false,
        message: 'Tool execution failed: $error',
        errorCode: AssistantErrorCode.executionFailed,
      );
    }
  }
}
```

### 3.3 Hash 级循环检测（借鉴 OpenClaw tool-loop-detection.ts）

```dart
class ToolCallHistory {
  static const int maxHistorySize = 30;
  static const int warningThreshold = 5;    // 私人助手场景比 OpenClaw 更小
  static const int criticalThreshold = 8;
  static const int globalCircuitBreaker = 12;
  
  final List<ToolCallRecord> _history = [];
  
  LoopDetectionResult detectLoop(String toolName, Map<String, dynamic> args) {
    final argsHash = _hashArgs(toolName, args);
    
    // 检测器 1: 全局熔断
    final noProgressStreak = _getNoProgressStreak(toolName, argsHash);
    if (noProgressStreak >= globalCircuitBreaker) {
      return LoopDetectionResult.critical(
        detector: 'global_circuit_breaker',
        count: noProgressStreak,
        userMessage: '检测到重复操作，停止当前任务并尝试其他方式',
      );
    }
    
    // 检测器 2: Ping-Pong 检测（A→B→A→B 交替）
    final pingPong = _getPingPongStreak(argsHash);
    if (pingPong.count >= criticalThreshold && pingPong.noProgress) {
      return LoopDetectionResult.critical(
        detector: 'ping_pong',
        count: pingPong.count,
        userMessage: '检测到反复尝试，改用其他方式为您回答',
      );
    }
    
    // 检测器 3: 通用重复
    final repeatCount = _history.where(
      (r) => r.toolName == toolName && r.argsHash == argsHash
    ).length;
    if (repeatCount >= warningThreshold) {
      return LoopDetectionResult.warning(
        detector: 'generic_repeat',
        count: repeatCount,
        userMessage: '多次尝试相同操作未获得新信息',
      );
    }
    
    return LoopDetectionResult.ok();
  }
  
  void recordCall(String toolName, Map<String, dynamic> args) {
    _history.add(ToolCallRecord(
      toolName: toolName,
      argsHash: _hashArgs(toolName, args),
      timestamp: DateTime.now(),
    ));
    if (_history.length > maxHistorySize) _history.removeAt(0);
  }
  
  void recordOutcome(String toolName, Map<String, dynamic> args, 
      AssistantToolResult? result, {Object? error}) {
    final argsHash = _hashArgs(toolName, args);
    final resultHash = _hashResult(result, error);
    // 倒序查找匹配的未填 resultHash 的记录
    for (var i = _history.length - 1; i >= 0; i--) {
      final record = _history[i];
      if (record.toolName == toolName && 
          record.argsHash == argsHash && 
          record.resultHash == null) {
        record.resultHash = resultHash;
        break;
      }
    }
  }
  
  String _hashArgs(String toolName, Map<String, dynamic> args) {
    final normalized = Map.fromEntries(
      args.entries.where((e) => !e.key.startsWith('__')).toList()
        ..sort((a, b) => a.key.compareTo(b.key))
    );
    return '$toolName:${sha256(jsonEncode(normalized))}';
  }
  
  String _hashResult(AssistantToolResult? result, Object? error) {
    if (error != null) return 'error:${sha256(error.toString())}';
    if (result == null) return 'null';
    return sha256(jsonEncode({
      'success': result.success,
      'message': result.message,
      'dataKeys': result.data?.keys.toList()?..sort(),
    }));
  }
  
  int _getNoProgressStreak(String toolName, String argsHash) {
    // 检查连续相同 args+result 的调用次数
    String? lastResultHash;
    int streak = 0;
    for (var i = _history.length - 1; i >= 0; i--) {
      final r = _history[i];
      if (r.toolName != toolName || r.argsHash != argsHash) continue;
      if (r.resultHash == null) continue;
      if (lastResultHash == null) {
        lastResultHash = r.resultHash;
        streak = 1;
      } else if (r.resultHash == lastResultHash) {
        streak++;
      } else {
        break;
      }
    }
    return streak;
  }
}

class ToolCallRecord {
  ToolCallRecord({required this.toolName, required this.argsHash, required this.timestamp});
  final String toolName;
  final String argsHash;
  final DateTime timestamp;
  String? resultHash;
}

class LoopDetectionResult {
  final bool blocked;       // critical → 阻止执行
  final bool warned;        // warning → 注入提示但不阻止
  final String detector;
  final int count;
  final String userMessage;
  
  LoopDetectionResult.ok() : blocked = false, warned = false, detector = '', count = 0, userMessage = '';
  LoopDetectionResult.warning({required this.detector, required this.count, required this.userMessage}) 
    : blocked = false, warned = true;
  LoopDetectionResult.critical({required this.detector, required this.count, required this.userMessage}) 
    : blocked = true, warned = true;
}
```

### 3.4 工具结果评估（Assessment）

```dart
class ToolResultAssessor {
  const ToolResultAssessor();
  
  ToolAssessmentOutcome assess({
    required ReactPlanStep step,
    required AssistantToolResult result,
    required ReactRunState state,
    required ReactPolicy policy,
    required ToolCallHistory callHistory,
  }) {
    // 1. 工具失败
    if (!result.success) {
      return ToolAssessmentOutcome.toolFailed(
        userMessage: _shouldSuppress(step.toolName, result, policy)
          ? '暂时无法使用此功能，将用其他方式回答'
          : result.message,
        suppressed: _shouldSuppress(step.toolName, result, policy),
      );
    }
    
    // 2. 循环检测结果影响
    final loopResult = callHistory.detectLoop(step.toolName, step.arguments);
    if (loopResult.warned) {
      return ToolAssessmentOutcome.needDifferentApproach(
        userMessage: loopResult.userMessage,
      );
    }
    
    // 3. 搜索质量评分（仅搜索类工具）
    if (step.toolName.contains('search')) {
      final data = result.data ?? {};
      final qualityScore = (data['qualityScore'] as num?)?.toDouble() ?? 0.0;
      final reflectionRound = state.openQuestions
        .where((q) => q.startsWith('reflect_round:')).length;
      
      if (qualityScore < policy.reflectionQualityScoreMin &&
          reflectionRound < policy.reflectionMaxRounds) {
        return ToolAssessmentOutcome.needReflection(
          userMessage: '找到的信息不够全面，我来扩大搜索范围',
          qualityScore: qualityScore,
          reflectionRound: reflectionRound + 1,
        );
      }
    }
    
    // 4. Replan 检查（coverage/confidence/freshness）
    final observation = buildToolObservation(step.toolName, result);
    final needsReplan = ReactReflector().shouldReplan(
      state: state, lastStepSuccess: true,
      lastObservation: observation, policy: policy,
    );
    if (needsReplan) {
      return ToolAssessmentOutcome.needReplan(
        userMessage: '还需要更多信息来完整回答您的问题',
      );
    }
    
    // 5. 结果充分
    return ToolAssessmentOutcome.sufficient(
      userMessage: '信息充分，准备分析',
    );
  }
}

enum ToolAssessmentType {
  sufficient,
  needReflection,
  needReplan,
  needDifferentApproach,
  toolFailed,
  budgetExhausted,
}

class ToolAssessmentOutcome {
  final ToolAssessmentType type;
  final String userMessage;
  final bool suppressed;
  final double? qualityScore;
  final int? reflectionRound;
  // 工厂构造器...
}
```

---

## 四、事件协议完整规格

### 4.1 内部 Trace 事件（引擎层产生）

```dart
enum AssistantTraceEventType {
  // 生命周期
  lifecycleStart,
  lifecycleEnd,
  
  // LLM 交互
  assistantDelta,        // LLM 完整输出（含 toolCalls）
  thinkingStarted,       // 每轮推理开始
  thinkingProgress,      // 思考 delta（SSE 流）
  streamDelta,           // 合成阶段 delta
  
  // 工具
  toolStart,
  toolResult,
  toolError,
  searchStarted,         // search 类工具特化
  searchCompleted,
  searchQueryGenerated,
  
  // 规划
  planStarted,
  planCompleted,
  replanTriggered,
  
  // 评估（新增）
  assessmentStarted,     // 开始评估工具结果
  assessmentResult,      // 评估结论
  loopDetected,          // 循环检测告警/阻断
  
  // 自检
  selfCheckResult,
  
  // Skill
  skillStart,
  skillResult,
  skillError,
  
  // 子 agent
  subagentStart,
  subagentResult,
  subagentError,
  
  // 答案
  answerStarted,
  answerDelta,
  answerCompleted,
}
```

### 4.2 用户阶段事件（UI 层消费）

```dart
enum UserPhaseEventType {
  // ── 固定阶段 ──
  understandingStarted,
  understandingThinking,    // SSE delta
  analyzingStarted,
  analyzingThinking,        // SSE delta
  answeringStarted,
  answeringDelta,           // SSE delta
  answeringCompleted,
  
  // ── 工具阶段（元数据驱动）──
  toolReasoningStarted,     // "为什么要搜索..."
  toolReasoningThinking,    // 工具推理 SSE delta
  toolExecutionStarted,     // "正在搜索相关资料"
  toolExecutionProgress,    // "检索查询: xxx"
  toolExecutionCompleted,   // "已找到 5 篇相关资料"
  
  // ── 评估阶段 ──
  toolAssessmentStarted,    // "正在检查信息是否充分..."
  toolAssessmentResult,     // "信息充分" / "补充搜索" / "暂不可用"
  
  // ── 安全降级 ──
  loopDegraded,             // "遇到困难，基于已有信息回答"
}
```

### 4.3 完整翻译表

```
内部 trace                                                  → 用户事件
──────────────────────────────────────────────────────────────────────────
planStarted                                                 → understandingStarted
thinkingStarted (iteration=1, evidence=empty)               → understandingStarted
thinkingProgress (evidence=empty)                           → understandingThinking {delta}
                                                            
toolStart (ANY toolName)                                    → toolExecutionStarted {toolName, meta.startLabel}
searchStarted (toolName=*search*)                           → toolExecutionProgress {query}
toolResult (ANY toolName, success=true)                     → toolExecutionCompleted {toolName, meta.completedTemplate(data)}
toolError (ANY toolName)                                    → toolAssessmentResult {type=toolFailed, meta or message}
                                                            
assessmentStarted                                           → toolAssessmentStarted
assessmentResult (type=sufficient)                          → toolAssessmentResult {type=sufficient, "信息充分"}
assessmentResult (type=needReflection)                      → toolAssessmentResult {type=needMoreSearch, "扩大搜索"}
assessmentResult (type=needReplan)                          → toolAssessmentResult {type=needMoreSearch, "需要更多信息"}
assessmentResult (type=toolFailed, suppressed)              → toolAssessmentResult {type=toolFailed, "暂不可用"}
                                                            
loopDetected (level=warning)                                → toolAssessmentResult {type=needDifferentApproach}
loopDetected (level=critical)                               → loopDegraded {userMessage}
                                                            
thinkingStarted (evidence=non-empty)                        → analyzingStarted
thinkingProgress (evidence=non-empty)                       → analyzingThinking {delta}
                                                            
streamDelta (stage=synthesis)                               → answeringDelta {delta}
lifecycleEnd                                                → answeringCompleted
                                                            
state.stopReason = budget/iteration/empty                   → loopDegraded {对应用户文案}
synthesisReadiness.ready = false                            → toolAssessmentResult {gapFill, "信息不完整"}
```

---

## 五、SSE 流式规格

### 5.1 LlmProvider 改造

```dart
abstract class AssistantLlmProvider {
  // 现有：同步调用
  Future<AssistantModelOutput> reason({...});
  
  // 现有：纯流式（合成用）
  Future<String> reasonStream({..., void Function(String delta) onDelta});
  
  // 改造：reason() 增加可选 onDelta
  Future<AssistantModelOutput> reason({
    ...,
    void Function(String delta)? onDelta,  // 新增
  });
}

class OpenAiCompatibleLlmProvider implements AssistantLlmProvider {
  @override
  Future<AssistantModelOutput> reason({..., void Function(String delta)? onDelta}) async {
    if (onDelta != null) {
      // 走 SSE 路径，逐 token 回调 onDelta，最终拼接完整输出
      return _requestCompletionWithStreaming(
        ..., onDelta: onDelta,
      );
    }
    // 向后兼容：无 onDelta 走普通 POST
    return _requestCompletion(...);
  }
}
```

### 5.2 思考内容提取策略

```dart
String? extractThinkingText(String rawOutput) {
  // 策略 1: <think> 标签（DeepSeek-R1 / QwQ 等）
  final thinkMatch = RegExp(r'<think>([\s\S]*?)</think>').firstMatch(rawOutput);
  if (thinkMatch != null) return thinkMatch.group(1)?.trim();
  
  // 策略 2: JSON 中的 thinkingText 字段
  try {
    final json = jsonDecode(rawOutput);
    if (json is Map && json['thinkingText'] is String) {
      return json['thinkingText'] as String;
    }
  } catch (_) {}
  
  // 策略 3: 纯文本（非 JSON）
  if (!rawOutput.trimLeft().startsWith('{')) {
    return rawOutput.trim();
  }
  
  return null;
}
```

### 5.3 流式时序（以"深圳天气"为例）

```
T+0ms     → understandingStarted
T+100ms   → understandingThinking("用户询问深圳")
T+200ms   → understandingThinking("天气，这是一个实时查询")
T+400ms   → understandingThinking("我将获取位置信息并搜索天气数据")
T+500ms   → (LLM 完成，决定调用 local_context + web_search)

T+510ms   → toolExecutionStarted(local_context, "正在获取您的位置")
T+800ms   → toolExecutionCompleted(local_context, "已定位到 深圳")

T+810ms   → toolExecutionStarted(web_search, "正在搜索相关资料")
T+820ms   → toolExecutionProgress(web_search, "检索查询: 深圳天气预报")
T+2500ms  → toolExecutionCompleted(web_search, "已找到 5 篇相关资料")

T+2510ms  → toolAssessmentStarted("正在检查信息是否充分")
T+2520ms  → toolAssessmentResult(sufficient, "信息充分，准备分析")

T+2530ms  → analyzingStarted
T+2600ms  → analyzingThinking("搜索结果显示深圳今日")
T+2700ms  → analyzingThinking("气温 22-28°C，多云")
T+2900ms  → analyzingThinking("来源: 中国气象局")

T+3000ms  → answeringStarted
T+3100ms  → answeringDelta("## 深圳今日天气\n\n")
T+3200ms  → answeringDelta("今天深圳多云，气温")
T+3400ms  → answeringDelta(" 22-28°C...")
T+4000ms  → answeringCompleted
```

---

## 六、工具元数据规格

### 6.1 userInteraction schema

```typescript
interface ToolUserInteraction {
  phaseTitle: string;         // "搜索资料"
  phaseIcon: string;          // "search" | "location" | "photo" | "memory" | "fetch"
  
  reasoning: {
    label: string;            // "搜索策略设计"
    promptHint: string;       // 注入 system message，引导 thinkingText
    example: string;          // few-shot 示例
  };
  
  executing: {
    startLabel: string;       // "正在搜索相关资料"
    progressTemplate: string; // "检索查询：{{query}}"（mustache 模板）
    completedTemplate: string;// "已找到 {{referenceCount}} 篇相关资料"
  };
  
  resultDisplay: {
    showKeywords: boolean;    // 显示搜索关键词？
    showReferences: boolean;  // 显示参考来源列表？
    referenceCountPath?: string;   // "references.length"
    referenceTitlePath?: string;   // "references[].title"
    referenceSourcePath?: string;  // "references[].source"
    summaryPath?: string;          // "city"（直接取值展示）
  };
  
  replanLabel: string | null; // "补充搜索更多资料" | null（不支持 replan）
}
```

### 6.2 ToolMetadataRegistry 新增方法

```dart
class ToolMetadataRegistry {
  // 现有方法...
  
  /// 获取工具的用户交互元数据
  ToolUserInteraction? userInteractionForTool(String toolName) {
    final meta = _catalog[toolName];
    if (meta == null) return null;
    final ui = meta['userInteraction'] as Map?;
    if (ui == null) return null;
    return ToolUserInteraction.fromJson(ui.cast<String, dynamic>());
  }
  
  /// 获取工具的 prompt hint（用于注入 system message）
  String? promptHintForTool(String toolName) {
    return userInteractionForTool(toolName)?.reasoning.promptHint;
  }
  
  /// 解析完成标签模板（用 mustache 替换变量）
  String resolveTemplate(String template, Map<String, dynamic> data) {
    return template.replaceAllMapped(
      RegExp(r'\{\{(\w+)\}\}'),
      (m) => '${data[m.group(1)] ?? m.group(0)}',
    );
  }
}
```

---

## 七、提示词规格

### 7.1 output contract v4 增加 thinkingText

```json
{
  "contractVersion": "assistant_turn_v4",
  "thinkingText": "(string) 用户可见的思考过程，自然中文，禁止 JSON 键名或技术术语",
  "decision": {
    "nextAction": "tool_call | answer | ask_user",
    "confidence": 0.85,
    "domainId": "weather"
  },
  "toolPlan": [...],
  "userMarkdown": "...",
  "selfCheck": {...}
}
```

### 7.2 phaseHint 注入模板

```json
{
  "understanding": {
    "hint": "你正在「理解问题」阶段。请在 thinkingText 字段中用自然语言描述：\n1. 用户想知道什么\n2. 你决定使用哪些工具、为什么\n3. 工具参数的设计理由\n\n注意：thinkingText 面向用户实时展示，用口语化中文。"
  },
  "analyzing": {
    "hint": "你正在「分析资料」阶段。请在 thinkingText 字段中用自然语言描述：\n1. 工具返回了哪些关键信息\n2. 哪些信息最可靠\n3. 你从中得出的结论\n\n注意：thinkingText 面向用户实时展示。"
  }
}
```

---

## 八、循环安全完整规格

### 8.1 安全阀清单

| 安全阀 | 触发条件 | 处理 | 用户事件 |
|--------|---------|------|---------|
| 迭代上限 | `iteration >= maxIterations` | 退出 while 循环 | `loopDegraded("已收集到部分信息")` |
| 工具预算 | `usedTools >= toolBudget` | 退出 for 循环 | `loopDegraded("已收集到部分信息")` |
| 反思轮次 | `reflectionRound >= reflectionMaxRounds` | 不再注入反思提示 | (无额外事件) |
| 空迭代 | `consecutiveEmptyIterations >= 2` | 退出 while 循环 | `loopDegraded("遇到困难")` |
| 通用重复 | `generic_repeat >= warningThreshold` | 注入警告 | `toolAssessmentResult(needDifferentApproach)` |
| Ping-Pong | `ping_pong >= criticalThreshold` | 阻断工具 | `loopDegraded("检测到反复尝试")` |
| 全局熔断 | `no_progress >= globalCircuitBreaker` | 阻断工具 | `loopDegraded("检测到重复操作")` |
| LLM 降级 | `output.degraded == true` | 提前退出 | `loopDegraded("服务暂时繁忙")` |
| LLM 超时 | HTTP timeout | 提前退出 | `loopDegraded("响应超时")` |
| 合成补齐 | `synthesisReadiness == false` | 再跑一轮 | `toolAssessmentResult(gapFill)` |

### 8.2 每个退出路径的 finalText 策略

| stopReason | finalText 来源 | 降级? |
|---|---|---|
| `model_answered_without_tools` | `output.text` | 仅当 `output.degraded` |
| `plan_step_without_tool` | `output.text` | 否 |
| `tool_budget_exhausted` | 最后一次 `assistantDelta` trace | 否 |
| `consecutive_empty_iterations` | 最后一次 `assistantDelta` trace，或兜底文案 | 是 |
| `loop_detected_critical` | 最后一次有效 trace，或兜底文案 | 是 |
| `null`（正常结束） | 最后一次 `assistantDelta` trace | 否 |

---

## 九、新工具规划（OpenClaw 对标）

### 9.1 P0 优先级

#### memory_search — 长期记忆语义检索

```json
{
  "toolName": "memory_search",
  "displayName": "记忆检索",
  "openAiFunction": {
    "name": "memory_search",
    "description": "搜索用户的长期记忆，包括偏好、历史对话要点、重要日期等",
    "parameters": {
      "type": "object",
      "properties": {
        "query": {"type": "string", "description": "语义搜索查询"},
        "maxResults": {"type": "integer", "description": "最大返回数", "default": 5}
      },
      "required": ["query"]
    }
  },
  "userInteraction": {
    "phaseTitle": "回忆相关信息",
    "phaseIcon": "memory",
    "reasoning": {
      "label": "记忆检索",
      "promptHint": "请在 thinkingText 中解释你为什么要检索记忆、你期望找到什么",
      "example": "用户之前提到过喜欢粤菜，我来回忆一下相关偏好。"
    },
    "executing": {
      "startLabel": "正在回忆相关信息",
      "progressTemplate": "检索：{{query}}",
      "completedTemplate": "回忆起 {{resultCount}} 条相关信息"
    },
    "resultDisplay": {"showReferences": false, "summaryPath": "results[0].text"},
    "replanLabel": null
  }
}
```

#### web_fetch — URL 内容深度阅读

```json
{
  "toolName": "web_fetch",
  "displayName": "网页阅读",
  "openAiFunction": {
    "name": "web_fetch",
    "description": "抓取指定 URL 的网页内容，提取正文转换为 markdown",
    "parameters": {
      "type": "object",
      "properties": {
        "url": {"type": "string", "description": "要抓取的 URL"},
        "maxChars": {"type": "integer", "description": "最大字符数", "default": 10000}
      },
      "required": ["url"]
    }
  },
  "userInteraction": {
    "phaseTitle": "阅读网页",
    "phaseIcon": "article",
    "reasoning": {
      "label": "深度阅读",
      "promptHint": "请在 thinkingText 中解释为什么需要深入阅读这个页面",
      "example": "搜索结果中有一篇气象局的详细预报，我来仔细阅读。"
    },
    "executing": {
      "startLabel": "正在阅读网页内容",
      "progressTemplate": "抓取：{{url}}",
      "completedTemplate": "已阅读 {{charCount}} 字内容"
    },
    "resultDisplay": {"showReferences": false, "summaryPath": "title"},
    "replanLabel": "阅读更多来源"
  }
}
```

### 9.2 P1 优先级

- `calendar_query`：日历查询（私人助手核心场景）
- `reminder_set`：提醒设置

### 9.3 P2 优先级

- `image_analyze`：图片理解
- `tts_speak`：语音播报

---

## 十、涉及文件改动清单

### Phase 0: 工具元数据层

| 文件 | 改动 |
|------|------|
| `tools/catalog/tool_catalog.meta.json` | 每个 tool 新增 `userInteraction` |
| `tools/metadata/tool_metadata_registry.dart` | 新增 `userInteractionForTool()`, `promptHintForTool()`, `resolveTemplate()` |

### Phase 1: 提示词层

| 文件 | 改动 |
|------|------|
| `prompts/global/phase.output_contract.plan.md` | 增加 `thinkingText` 字段规范 |
| `prompts/global/phase.output_contract.answer.md` | 增加 `thinkingText` 字段规范 |
| `prompts/global/planner.global_plan.md` | 增加阶段感知 thinkingText 指导 |
| `config/user_phase_hints.json` | **新建**：固定阶段 phaseHint 模板 |

### Phase 2: SSE 流式

| 文件 | 改动 |
|------|------|
| `engine/llm_provider.dart` | `reason()` 增加 `onDelta` 回调 |

### Phase 3: ReactRuntime 阶段判定

| 文件 | 改动 |
|------|------|
| `engine/react_runtime.dart` | `_determineUserPhase()`, `_buildPhaseHint()`, SSE onDelta 传递 |
| `engine/react_state.dart` | 新增 `consecutiveEmptyIterations` |

### Phase 3b: 工具生命周期 + 循环检测 + 评估闭环

| 文件 | 改动 |
|------|------|
| `tools/tool_registry.dart` | Hook 链改造：before/after + `ToolCallHistory` |
| `tools/tool_loop_detection.dart` | **新建**：`ToolCallHistory`, `LoopDetectionResult` |
| `engine/tool_result_assessor.dart` | **新建**：`ToolResultAssessor`, `ToolAssessmentOutcome` |
| `engine/react_runtime.dart` | 集成 assessment + 循环检测 + 降级事件 |

### Phase 4: 事件翻译层

| 文件 | 改动 |
|------|------|
| `protocol/trace_events.dart` | 新增 `UserPhaseEventType` 枚举 + assessment 事件类型 |
| `app/capability_gateway.dart` | `_emitSemanticEvent()` 重构为翻译表模式 |

### Phase 5-6: UI 层

| 文件 | 改动 |
|------|------|
| `ui/chat/pages/chat_detail_page.dart` | `_phaseTitle/_phaseSummary` 改为元数据驱动 |
| `ui/chat/widgets/message/chat_message_bubble.dart` | timeline card 支持流式思考 + resultDisplay |
| `core/constants/ui_text_constants.dart` | 替换固定阶段文案 |
| `engine/agent_loop.dart` | `_buildUiPhaseTimelineV1` 重构 |

### Phase 7: E2E 验证

| 文件 | 改动 |
|------|------|
| `test/personal_assistant/assistant_run_e2e_test.dart` | 新增阶段事件 + 流式思考 + 无内部字符串断言 |

### Phase 8: 新工具（可选，单独迭代）

| 文件 | 改动 |
|------|------|
| `tools/web_fetch_tool.dart` | **新建**：URL 内容抓取 |
| `tools/memory_search_tool.dart` | **新建**：记忆检索 |
| `tools/catalog/tool_catalog.meta.json` | 新增 web_fetch, memory_search 定义 |
| `app/assistant_runtime.dart` | 注册新工具 |
