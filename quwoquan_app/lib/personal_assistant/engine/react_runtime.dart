import 'dart:convert';

import 'package:flutter/services.dart' show rootBundle;
import 'package:quwoquan_app/assistant/contracts/assistant_turn_contract.dart';
import 'package:quwoquan_app/personal_assistant/contracts/runtime_policies.dart';
import 'package:quwoquan_app/personal_assistant/engine/llm_provider.dart';
import 'package:quwoquan_app/personal_assistant/engine/react_planner.dart';
import 'package:quwoquan_app/personal_assistant/engine/react_state.dart';
import 'package:quwoquan_app/personal_assistant/engine/tool_execution_guard.dart';
import 'package:quwoquan_app/personal_assistant/engine/tool_result_assessor.dart';
import 'package:quwoquan_app/personal_assistant/engine/tool_result_truncator.dart';
import 'package:quwoquan_app/personal_assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/personal_assistant/tools/metadata/tool_metadata_registry.dart';
import 'package:quwoquan_app/personal_assistant/tools/tool_registry.dart';
import 'package:quwoquan_app/personal_assistant/tools/tool_schema.dart';

class ReactRuntimeResult {
  const ReactRuntimeResult({
    required this.finalText,
    required this.traces,
    this.degraded = false,
    this.failureCode = '',
  });

  final String finalText;
  final List<AssistantTraceEvent> traces;

  /// true 表示本次 run 产出的是降级内容，不应写入 session/memory。
  final bool degraded;

  /// 对应 [AssistantFailureCode] 或 [AssistantErrorCode.name]，空串表示无错误。
  final String failureCode;
}

class ReactRuntime {
  ReactRuntime({
    required AssistantLlmProvider llmProvider,
    required AssistantToolRegistry toolRegistry,
    ReactPlanner? planner,
    ReactReflector? reflector,
    ToolMetadataRegistry? toolMetadataRegistry,
  }) : _llmProvider = llmProvider,
       _toolRegistry = toolRegistry,
       _planner = planner ?? const ReactPlanner(),
       _reflector = reflector ?? const ReactReflector(),
       _toolMetadataRegistry = toolMetadataRegistry,
       _assessor = ToolResultAssessor(),
       _executionGuard = ToolExecutionGuard(
         permissions: const <String, ToolPermission>{
           'intent_bridge': ToolPermission(requireConfirmation: true),
           'scheduler': ToolPermission(requireConfirmation: true),
           'app_action': ToolPermission(
             requireConfirmation: true,
             allowedSchemes: ['tel', 'sms', 'mailto', 'maps'],
           ),
         },
       ),
       _resultTruncator = const ToolResultTruncator();

  final AssistantLlmProvider _llmProvider;
  final AssistantToolRegistry _toolRegistry;
  final ReactPlanner _planner;
  final ReactReflector _reflector;
  final ToolMetadataRegistry? _toolMetadataRegistry;
  final ToolResultAssessor _assessor;
  final ToolExecutionGuard _executionGuard;
  final ToolResultTruncator _resultTruncator;
  static const String _reactPolicyPath =
      'assets/personal_assistant/config/react_policy.json';
  static const String _phaseHintsPath =
      'assets/personal_assistant/config/user_phase_hints.json';
  ReactPolicy _reactPolicy = ReactPolicy.defaults;
  Future<void>? _reactPolicyLoading;
  Map<String, dynamic> _phaseHintsConfig = const <String, dynamic>{};
  Future<void>? _phaseHintsLoading;
  static const int _maxConsecutiveEmptyIterations = 2;

  List<String> listAvailableToolNames() {
    return _toolRegistry
        .listTools()
        .map((tool) => tool.name)
        .toList(growable: false);
  }

  /// Streams synthesis output token by token using SSE if provider supports it.
  /// Calls [onDelta] for each token, and emits [streamDelta] trace events.
  Future<String> streamSynthesis({
    required List<Map<String, dynamic>> messages,
    required String goal,
    required void Function(String delta) onDelta,
    Map<String, dynamic> templateContext = const <String, dynamic>{},
    Map<String, dynamic> templateVariables = const <String, dynamic>{},
    String templateId = 'synthesizer.final_answer',
    String templateVersion = '',
    String sessionId = '',
    String? runId,
    String? traceId,
    void Function(AssistantTraceEvent event)? onTraceEvent,
  }) async {
    final provider = _llmProvider;
    void forwardDelta(String delta) {
      onDelta(delta);
      onTraceEvent?.call(
        AssistantTraceEvent(
          type: AssistantTraceEventType.streamDelta,
          message: delta,
          timestamp: DateTime.now(),
          runId: runId,
          traceId: traceId,
          data: const <String, dynamic>{'stage': 'synthesis'},
        ),
      );
    }

    if (provider is SwitchableAssistantLlmProvider) {
      return provider.reasonStream(
        messages: messages,
        availableTools: const <String>[],
        onDelta: forwardDelta,
        templateContext: templateContext,
        templateVariables: templateVariables,
        templateId: templateId,
        templateVersion: templateVersion,
        sessionId: sessionId,
        runId: runId ?? '',
        traceId: traceId ?? '',
      );
    }

    if (provider is OpenAiCompatibleLlmProvider) {
      return provider.reasonStream(
        messages: messages,
        availableTools: const <String>[],
        onDelta: forwardDelta,
        templateContext: templateContext,
        templateVariables: templateVariables,
        templateId: templateId,
        templateVersion: templateVersion,
        sessionId: sessionId,
        runId: runId ?? '',
        traceId: traceId ?? '',
      );
    }
    return '';
  }

  Future<ReactRuntimeResult> run({
    required List<Map<String, dynamic>> messages,
    required int maxIterations,
    String goal = '',
    List<String>? availableToolNamesOverride,
    Map<String, dynamic> templateContext = const <String, dynamic>{},
    Map<String, dynamic> templateVariables = const <String, dynamic>{},
    String templateId = 'planner.global_plan',
    String templateVersion = '',
    String sessionId = '',
    String? runId,
    String? traceId,
    void Function(AssistantTraceEvent event)? onTraceEvent,
    LlmCallOptions? callOptions,
    void Function(String delta)? onDelta,
  }) async {
    await _ensureReactPolicyLoaded();
    await _ensurePhaseHintsLoaded();
    await _toolMetadataRegistry?.ensureLoaded();
    _toolRegistry.resetCallHistory();
    _assessor.reset();
    _assessor.problemClass =
        (templateVariables['problemClass'] as String?)?.trim() ?? '';
    _executionGuard.reset();
    final goalText = goal.isEmpty
        ? (messages.lastWhere(
                (m) => m['role'] == 'user',
                orElse: () => const <String, String>{'content': ''},
              )['content'] ??
              '')
        : goal;
    final executionShell = _resolveExecutionShell(templateVariables);
    final state = ReactRunState(
      goal: goalText,
      maxIterations: maxIterations,
      toolBudget: executionShell.toolBudget,
    );
    final traces = <AssistantTraceEvent>[];
    void pushTrace(AssistantTraceEvent event) {
      traces.add(event);
      onTraceEvent?.call(event);
    }

    pushTrace(
      AssistantTraceEvent(
        type: AssistantTraceEventType.lifecycleStart,
        message: 'agent loop started',
        timestamp: DateTime.now(),
        runId: runId,
        traceId: traceId,
        visibility: TraceVisibility.system,
      ),
    );
    pushTrace(
      AssistantTraceEvent(
        type: AssistantTraceEventType.planStarted,
        message: '开始规划: $goalText',
        timestamp: DateTime.now(),
        runId: runId,
        traceId: traceId,
        data: <String, dynamic>{
          'goal': goalText,
          'templateId': templateId,
          'maxIterations': maxIterations,
        },
      ),
    );

    var finalText = '';
    while (!state.shouldStopByIteration && !state.shouldStopByBudget) {
      state.iteration += 1;
      final availableToolNames =
          availableToolNamesOverride ?? listAvailableToolNames();
      pushTrace(
        AssistantTraceEvent(
          type: AssistantTraceEventType.thinkingStarted,
          message: '第 ${state.iteration} 轮推理',
          timestamp: DateTime.now(),
          runId: runId,
          traceId: traceId,
          data: <String, dynamic>{
            'iteration': state.iteration,
            'goal': state.goal,
            'availableTools': availableToolNames,
          },
        ),
      );
      pushTrace(
        AssistantTraceEvent(
          type: AssistantTraceEventType.lifecycleStart,
          message: 'llm request iteration ${state.iteration}',
          timestamp: DateTime.now(),
          runId: runId,
          traceId: traceId,
          visibility: TraceVisibility.internal,
          data: <String, dynamic>{
            'iteration': state.iteration,
            'goal': state.goal,
            'availableTools': availableToolNames,
            'messages': messages,
          },
        ),
      );
      // Inject phase hint for user-visible thinking guidance
      final currentPhase = _determineUserPhase(state);
      final phaseHint = _buildPhaseHint(currentPhase, availableToolNames);
      if (phaseHint.isNotEmpty) {
        messages.add(<String, String>{'role': 'system', 'content': phaseHint});
      }

      pushTrace(
        AssistantTraceEvent(
          type: AssistantTraceEventType.thinkingProgress,
          message: currentPhase == 'analyzing' ? '正在深入分析...' : '正在思考...',
          timestamp: DateTime.now(),
          runId: runId,
          traceId: traceId,
          data: <String, dynamic>{
            'phase': currentPhase,
            'iteration': state.iteration,
            'extracted': true,
          },
        ),
      );
      var anyDeltaForwarded = false;
      final wrappedOnDelta = onDelta != null
          ? (String delta) {
              if (delta.trim().isEmpty) return;
              anyDeltaForwarded = true;
              pushTrace(
                AssistantTraceEvent(
                  type: AssistantTraceEventType.thinkingProgress,
                  message: delta,
                  timestamp: DateTime.now(),
                  runId: runId,
                  traceId: traceId,
                  data: <String, dynamic>{
                    'phase': currentPhase,
                    'iteration': state.iteration,
                    'streaming': true,
                    'extracted': true,
                  },
                ),
              );
              onDelta(delta);
            }
          : null;
      final output = await _llmProvider.reason(
        messages: messages,
        availableTools: availableToolNames,
        templateContext: templateContext,
        templateVariables: templateVariables,
        templateId: templateId,
        templateVersion: templateVersion,
        sessionId: sessionId,
        runId: runId ?? '',
        traceId: traceId ?? '',
        callOptions: callOptions,
        onDelta: wrappedOnDelta,
      );
      final currentDomainId =
          (templateVariables['domainId'] as String?)?.trim() ?? '';
      final contextEnvelope =
          (templateVariables['contextEnvelope'] as Map?)
              ?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      pushTrace(
        AssistantTraceEvent(
          type: AssistantTraceEventType.assistantDelta,
          message: output.text,
          timestamp: DateTime.now(),
          runId: runId,
          traceId: traceId,
          visibility: TraceVisibility.system,
          data: <String, dynamic>{
            'iteration': state.iteration,
            'degraded': output.degraded,
            'modelPath': output.modelPath,
            'toolCalls': output.toolCalls
                .map(
                  (call) => <String, dynamic>{
                    'name': call.name,
                    'arguments': call.arguments,
                  },
                )
                .toList(growable: false),
            'searchQueries': _extractPlannedSearchQueries(output.toolCalls),
            if (output.usageEntries.isNotEmpty)
              'usageEntries': output.usageEntries,
          },
        ),
      );
      final extractedThinking = _extractBestThinking(
        output.text,
        output.reasoningText,
      );
      if (extractedThinking.isNotEmpty && !anyDeltaForwarded) {
        pushTrace(
          AssistantTraceEvent(
            type: AssistantTraceEventType.thinkingProgress,
            message: extractedThinking,
            timestamp: DateTime.now(),
            runId: runId,
            traceId: traceId,
            data: <String, dynamic>{
              'phase': currentPhase,
              'iteration': state.iteration,
              'extracted': true,
            },
          ),
        );
      }
      // 当模型不走 native function calling（如 mimo-v2-flash），尝试从 JSON 正文
      // 的 toolPlan / nextAction='tool_call' 字段里解析工具调用。
      // 合成阶段（availableToolNames 为空）不解析 JSON 工具调用，
      // 防止模型输出 nextAction='tool_call' 时误触发工具执行。
      // For models without native function calling, also check reasoning text
      // since some models (MIMO) put the JSON action plan inside reasoning.
      final extractSource = output.text.trim().isNotEmpty
          ? output.text
          : output.reasoningText;
      final rawToolCalls = output.hasToolCalls
          ? output.toolCalls
          : (availableToolNames.isEmpty
                ? const <AssistantToolCall>[]
                : _extractToolCallsFromJsonText(extractSource));
      final effectiveToolCalls = _sanitizeToolCalls(
        rawToolCalls,
        shell: executionShell,
      );
      for (final call in effectiveToolCalls) {
        if (!_isRetrievalLikeTool(call.name)) continue;
        final plannedTasks = _coerceSearchTasks(call.arguments['queryTasks']);
        if (plannedTasks.isEmpty) continue;
        pushTrace(
          AssistantTraceEvent(
            type: AssistantTraceEventType.searchQueryGenerated,
            message: '生成检索计划',
            timestamp: DateTime.now(),
            runId: runId,
            traceId: traceId,
            toolCallId: call.id,
            data: <String, dynamic>{
              'toolName': call.name,
              'problemClass': executionShell.problemClass,
              'query': (call.arguments['query'] as String?)?.trim() ?? '',
              'queryTasks': plannedTasks,
              if (call.arguments['queryNormalization'] is Map)
                'queryNormalization':
                    (call.arguments['queryNormalization'] as Map)
                        .cast<String, dynamic>(),
            },
          ),
        );
      }
      // Track consecutive empty iterations for deadlock detection
      final isEmptyOutput =
          output.text.trim().isEmpty && effectiveToolCalls.isEmpty;
      if (isEmptyOutput) {
        state.consecutiveEmptyIterations += 1;
      } else {
        state.consecutiveEmptyIterations = 0;
      }

      if (state.consecutiveEmptyIterations >= _maxConsecutiveEmptyIterations) {
        state.stopReason = 'consecutive_empty_iterations';
        pushTrace(
          AssistantTraceEvent(
            type: AssistantTraceEventType.lifecycleEnd,
            message: 'loop degraded: consecutive empty iterations',
            timestamp: DateTime.now(),
            runId: runId,
            traceId: traceId,
            data: <String, dynamic>{
              'consecutiveEmptyIterations': state.consecutiveEmptyIterations,
              'userMessage': '这轮补不到更稳的信息了，我先把已经确认的内容整理给你。',
              'lifecycleOutcome': 'degraded',
            },
          ),
        );
        break;
      }

      if (effectiveToolCalls.isEmpty) {
        finalText = output.text;
        state.stopReason = 'model_answered_without_tools';
        if (output.degraded) {
          pushTrace(
            AssistantTraceEvent(
              type: AssistantTraceEventType.lifecycleEnd,
              message: 'agent loop finished (${state.stopReason})',
              timestamp: DateTime.now(),
              runId: runId,
              traceId: traceId,
            data: const <String, dynamic>{'lifecycleOutcome': 'degraded'},
            ),
          );
          return ReactRuntimeResult(
            finalText: finalText,
            traces: traces,
            degraded: true,
            failureCode: output.failureCode,
          );
        }
        break;
      }
      state.plan
        ..clear()
        ..addAll(
          _planner.buildPlan(
            userGoal: state.goal,
            suggestedToolCalls: effectiveToolCalls,
          ),
        );

      // OpenAI 协议要求：先把 assistant message（含 tool_calls）加入历史，
      // 然后每个 tool result message 必须有对应的 tool_call_id。
      // 当模型用 native function calling 时，保存原始 assistant message；
      // 否则（JSON 解析路径）合成一个兼容格式的 assistant message。
      if (output.rawAssistantToolCallsMessage != null) {
        // 原始 assistant message 已含 tool_calls，直接加入（用 Map 类型）
        final rawMsg = output.rawAssistantToolCallsMessage!;
        final rawToolCalls =
            (rawMsg['tool_calls'] as List?)?.cast<dynamic>() ??
            const <dynamic>[];
        final sanitizedToolCalls = rawToolCalls
            .asMap()
            .entries
            .map((entry) {
              final item = entry.value;
              if (item is! Map) return item;
              final sanitized = entry.key < effectiveToolCalls.length
                  ? effectiveToolCalls[entry.key]
                  : null;
              if (sanitized == null) return item;
              final function =
                  (item['function'] as Map?)?.cast<String, dynamic>() ??
                  const <String, dynamic>{};
              return <String, dynamic>{
                ...item.cast<String, dynamic>(),
                'function': <String, dynamic>{
                  ...function,
                  'arguments': jsonEncode(sanitized.arguments),
                },
              };
            })
            .toList(growable: false);
        messages.add(
          <String, dynamic>{
            'role': rawMsg['role'] ?? 'assistant',
            if (rawMsg['content'] != null) 'content': rawMsg['content'],
            'tool_calls': sanitizedToolCalls,
          }.map((k, v) => MapEntry(k, v)),
        );
      } else {
        // JSON 解析路径：为每个工具调用生成一个带 id 的 tool_calls 列表
        final syntheticToolCalls = effectiveToolCalls
            .map((call) {
              final callId = call.id.isNotEmpty
                  ? call.id
                  : 'call_${call.name}_${state.iteration}';
              return <String, dynamic>{
                'id': callId,
                'type': 'function',
                'function': <String, dynamic>{
                  'name': call.name,
                  'arguments': jsonEncode(call.arguments),
                },
              };
            })
            .toList(growable: false);
        messages.add(<String, dynamic>{
          'role': 'assistant',
          'content': null,
          'tool_calls': syntheticToolCalls,
        });
      }
      for (final step in state.plan) {
        if (step.toolName.isEmpty) {
          finalText = output.text;
          state.stopReason = 'plan_step_without_tool';
          break;
        }
        if (state.shouldStopByBudget) {
          state.stopReason = 'tool_budget_exhausted';
          break;
        }
        // Pre-execution guard: loop detection + permission check
        final guardResult = _executionGuard.checkBeforeExecution(
          step.toolName,
          step.arguments,
        );
        if (guardResult.isBlocked) {
          pushTrace(
            AssistantTraceEvent(
              type: AssistantTraceEventType.toolError,
              message: guardResult.reason,
              timestamp: DateTime.now(),
              runId: runId,
              traceId: traceId,
              toolCallId: step.id,
              data: <String, dynamic>{
                'guardBlocked': true,
                'reason': guardResult.reason,
              },
            ),
          );
          state.stopReason = 'guard_blocked';
          break;
        }
        if (guardResult.verdict == GuardVerdict.needsConfirmation) {
          pushTrace(
            AssistantTraceEvent(
              type: AssistantTraceEventType.toolStart,
              message: '需要确认: ${step.toolName}',
              timestamp: DateTime.now(),
              runId: runId,
              traceId: traceId,
              toolCallId: step.id,
              data: <String, dynamic>{
                'needsConfirmation': true,
                'toolName': guardResult.toolName,
                'args': guardResult.args,
              },
            ),
          );
        }
        state.usedTools += 1;
        final retrievalLike = _isRetrievalLikeTool(step.toolName);
        if (retrievalLike) {
          final query =
              (step.arguments['query'] ??
                      step.arguments['keyword'] ??
                      step.arguments['url'] ??
                      '')
                  .toString();
          pushTrace(
            AssistantTraceEvent(
              type: AssistantTraceEventType.searchStarted,
              message: query.isNotEmpty ? '检索: $query' : '开始检索',
              timestamp: DateTime.now(),
              runId: runId,
              traceId: traceId,
              toolCallId: step.id,
              data: <String, dynamic>{
                'toolName': step.toolName,
                'query': query,
                'problemClass': executionShell.problemClass,
              },
            ),
          );
        }
        pushTrace(
          AssistantTraceEvent(
            type: AssistantTraceEventType.toolStart,
            message: 'calling ${step.toolName}',
            timestamp: DateTime.now(),
            runId: runId,
            traceId: traceId,
            toolCallId: step.id,
            data: <String, dynamic>{
              'stepId': step.id,
              'toolName': step.toolName,
              'description': step.description,
              ...step.arguments,
              '__sessionId': sessionId,
              '__runId': runId ?? '',
              '__traceId': traceId ?? '',
              if (currentDomainId.isNotEmpty) '__domainId': currentDomainId,
              if (state.goal.trim().isNotEmpty) '__userGoal': state.goal.trim(),
              if (contextEnvelope.isNotEmpty)
                '__contextEnvelope': contextEnvelope,
            },
          ),
        );
        final toolArguments = <String, dynamic>{
          ...step.arguments,
          '__sessionId': sessionId,
          '__runId': runId ?? '',
          '__traceId': traceId ?? '',
          if (currentDomainId.isNotEmpty) '__domainId': currentDomainId,
          if (state.goal.trim().isNotEmpty) '__userGoal': state.goal.trim(),
          if (contextEnvelope.isNotEmpty) '__contextEnvelope': contextEnvelope,
        };
        final result = await _toolRegistry.execute(
          step.toolName,
          toolArguments,
        );
        final isOk = result.success;
        _executionGuard.recordExecutionResult(
          step.toolName,
          step.arguments,
          success: isOk,
          message: result.message,
          errorCode: result.errorCode.name,
        );
        final shouldSuppressToolErrorForUser =
            !isOk && _shouldSuppressToolErrorForUser(step.toolName, result);
        state.evidences.add(<String, dynamic>{
          'stepId': step.id,
          'tool': step.toolName,
          'success': result.success,
          'message': result.message,
          'data': result.data,
        });
        final traceData = <String, dynamic>{
          ...?result.data,
          'toolName': step.toolName,
          'problemClass': executionShell.problemClass,
          'retrievalLike': retrievalLike,
          if (!isOk && shouldSuppressToolErrorForUser) 'suppressed': true,
        };
        pushTrace(
          AssistantTraceEvent(
            type: isOk
                ? AssistantTraceEventType.toolResult
                : AssistantTraceEventType.toolError,
            message: result.message,
            timestamp: DateTime.now(),
            runId: runId,
            traceId: traceId,
            toolCallId: step.id,
            data: traceData.isEmpty ? null : traceData,
          ),
        );
        if (retrievalLike && isOk) {
          final refs = (result.data?['references'] as List?)?.length ?? 0;
          pushTrace(
            AssistantTraceEvent(
              type: AssistantTraceEventType.searchCompleted,
              message: '检索完成，获取 $refs 条结果',
              timestamp: DateTime.now(),
              runId: runId,
              traceId: traceId,
              toolCallId: step.id,
              data: <String, dynamic>{
                'toolName': step.toolName,
                'referenceCount': refs,
                'references': (result.data?['references'] as List?) ?? const <dynamic>[],
                'problemClass': executionShell.problemClass,
                'qualityScore':
                    (result.data?['qualityScore'] as num?)?.toDouble() ?? 0.0,
              },
            ),
          );
        }
        final toolObservation = _buildToolObservation(
          toolName: step.toolName,
          result: result,
        );
        // Truncate tool result to prevent context window overflow
        final rawContent = jsonEncode(toolObservation);
        final truncatedContent = _resultTruncator.truncate(rawContent);
        // OpenAI 协议要求：tool message 必须有 tool_call_id，对应 assistant message 里的 tool_calls[].id
        final effectiveCallId = step.toolCallId.isNotEmpty
            ? step.toolCallId
            : 'call_${step.toolName}_${state.iteration}';
        messages.add(<String, dynamic>{
          'role': 'tool',
          'tool_call_id': effectiveCallId,
          'content': truncatedContent,
        });
        if (!isOk) {
          final failureContext = _buildToolFailureContext(
            toolName: step.toolName,
            message: result.message,
            goal: state.goal,
            messages: messages,
          );
          messages.add(<String, String>{
            'role': 'system',
            'content':
                '工具调用失败上下文（供下一轮决策，不直接展示给用户）：\n'
                '${jsonEncode(failureContext)}\n'
                '请结合历史对话决定下一步：若缺少关键槽位则优先 ask_user；'
                '若关键槽位已齐但外部能力失败，则给出基于现有信息的稳妥降级答复，并说明是否值得重试。',
          });
        }
        // Layer 3 反思循环：当 web_search 质量评分不足时，注入反思提示驱动 LLM 重写查询
        if (step.toolName == 'web_search' && isOk) {
          final data =
              (result.data as Map?)?.cast<String, dynamic>() ??
              const <String, dynamic>{};
          final qualityScore =
              (data['qualityScore'] as num?)?.toDouble() ?? 0.0;
          final reflectionRound = state.openQuestions
              .where((q) => q.startsWith('reflect_round:'))
              .length;
          final allowedReflectionRounds =
              executionShell.reflectionBudget < _reactPolicy.reflectionMaxRounds
              ? executionShell.reflectionBudget
              : _reactPolicy.reflectionMaxRounds;
          if (qualityScore < _reactPolicy.reflectionQualityScoreMin &&
              reflectionRound < allowedReflectionRounds) {
            final roundLabel = 'reflect_round:${reflectionRound + 1}';
            state.openQuestions.add(roundLabel);
            final authorityDomains =
                (data['authorityDomains'] as List?)?.cast<String>() ??
                <String>[];
            final refs =
                (data['references'] as List?)?.cast<Map<String, dynamic>>() ??
                <Map<String, dynamic>>[];
            final snippets = refs
                .take(3)
                .map((r) => r['snippet'] ?? r['title'] ?? '')
                .where((s) => s.isNotEmpty)
                .toList();
            messages.add(<String, String>{
              'role': 'system',
              'content':
                  '本轮搜索质量评分过低（qualityScore=${qualityScore.toStringAsFixed(2)}），'
                  '请诊断失败原因并生成3条差异化重写查询词：\n'
                  '失败信息: ${result.message}\n'
                  '目标权威域: ${authorityDomains.join(", ")}\n'
                  '已检索片段摘要: ${snippets.join(" | ")}\n'
                  '这是第 ${reflectionRound + 1} 次反思（最多$allowedReflectionRounds次）。'
                  '请输出 JSON：failureReason（从 authority_domain_miss/query_too_generic/time_constraint_too_strict/provider_cache_stale/language_mismatch/missing_geo_context 中选）、'
                  'rewrittenQueries（3条，每条覆盖不同召回角度）、retryProvider。'
                  '然后重新调用 web_search 工具并选用不同 provider。\n'
                  '注意：重写查询词必须与已使用的查询词有实质性差异，避免重复失败。',
            });
          }
        }
        if (!isOk && !shouldSuppressToolErrorForUser) {
          finalText = result.message;
        } else if (!isOk && shouldSuppressToolErrorForUser) {
          messages.add(const <String, String>{
            'role': 'system',
            'content':
                '本轮外部检索能力暂不可用。请不要继续调用检索工具，改为基于当前上下文与已有知识直接回答用户问题，并明确说明无法联网检索最新数据。',
          });
        }

        // Skip reflection loop entirely when reflectionBudget == 0
        // (e.g. realtime_info / weather queries that should converge fast).
        final shouldSkipReflection = executionShell.reflectionBudget == 0;

        final replan = shouldSkipReflection
            ? false
            : _reflector.shouldReplan(
                state: state,
                lastStepSuccess: isOk,
                lastObservation: toolObservation,
                policy: _reactPolicy,
              );

        final assessment = _assessor.assess(
          state: state,
          lastStepSuccess: isOk,
          lastObservation: <String, dynamic>{
            ...toolObservation,
            if (result.data != null) 'data': result.data,
            if (!isOk && _shouldSuppressToolErrorForUser(step.toolName, result))
              'suppressed': true,
          },
          shouldReplan: replan,
          policy: _reactPolicy,
        );
        pushTrace(
          AssistantTraceEvent(
            type: AssistantTraceEventType.toolResult,
            message: assessment.userMessage,
            timestamp: DateTime.now(),
            runId: runId,
            traceId: traceId,
            data: <String, dynamic>{
              'assessmentType': assessment.type.name,
              'userMessage': assessment.userMessage,
              'shouldContinueLoop': assessment.shouldContinueLoop,
              'isAssessment': true,
              'referenceCount':
                  ((result.data?['referenceCount'] as num?)?.toInt() ??
                  ((result.data?['references'] as List?)?.length ?? 0)),
              if (result.data?['queryCount'] != null)
                'queryCount': result.data?['queryCount'],
              if (result.data?['queryLabels'] is List)
                'queryLabels': result.data?['queryLabels'],
              if (result.data?['coveredDimensions'] is List)
                'coveredDimensions': result.data?['coveredDimensions'],
            },
          ),
        );

        if (replan && assessment.shouldContinueLoop) {
          state.openQuestions.add('step ${step.id} result needs re-check');
          pushTrace(
            AssistantTraceEvent(
              type: AssistantTraceEventType.replanTriggered,
              message: assessment.userMessage,
              timestamp: DateTime.now(),
              runId: runId,
              traceId: traceId,
              data: <String, dynamic>{'reason': assessment.type.name},
            ),
          );
          break;
        }
      }
    }

    if (finalText.isEmpty) {
      // 循环退出但 finalText 未设置（模型持续调用工具直到迭代/预算耗尽）。
      // 尝试从 traces 中最后一次模型输出提取 userMarkdown 或完整 JSON 文本，
      // 避免用静态兜底文案覆盖有价值的模型输出。
      final lastDeltaIndex = traces.lastIndexWhere(
        (e) =>
            e.type == AssistantTraceEventType.assistantDelta &&
            e.message.trim().isNotEmpty,
      );
      if (lastDeltaIndex >= 0) {
        finalText = traces[lastDeltaIndex].message;
      } else {
        finalText = '本次任务已完成，但没有生成可展示结果。';
      }
    }

    pushTrace(
      AssistantTraceEvent(
        type: AssistantTraceEventType.lifecycleEnd,
        message: 'agent loop finished (${state.stopReason ?? 'normal_end'})',
        timestamp: DateTime.now(),
        runId: runId,
        traceId: traceId,
        data: const <String, dynamic>{'lifecycleOutcome': 'completed'},
      ),
    );
    // 检查 traces 中是否存在降级标记（工具预算耗尽后末次 LLM 也降级的场景）。
    final hasDegradedInTrace = traces.any(
      (e) =>
          e.type == AssistantTraceEventType.assistantDelta &&
          (e.data?['degraded'] == true),
    );
    return ReactRuntimeResult(
      finalText: finalText,
      traces: traces,
      degraded: hasDegradedInTrace,
    );
  }

  /// 判断工具错误是否应对用户静默（不直接把 result.message 作为 finalText 暴露）。
  /// 使用 [result.errorCode] 枚举，不依赖 result.message 文案内容，
  /// 消除工具实现的错误文案变更对此处行为的影响。
  bool _shouldSuppressToolErrorForUser(
    String toolName,
    AssistantToolResult result,
  ) {
    final rule = _reactPolicy.suppressRuleFor(toolName);
    if (rule == null) return false;
    final codeName = result.errorCode.name;
    if (!rule.errorCodes.contains(codeName)) return false;
    if (codeName != AssistantErrorCode.executionFailed.name) return true;
    final lowered = result.message.toLowerCase();
    for (final keyword in rule.messageKeywords) {
      final token = keyword.trim().toLowerCase();
      if (token.isNotEmpty && lowered.contains(token)) {
        return true;
      }
    }
    return false;
  }

  Map<String, dynamic> _buildToolFailureContext({
    required String toolName,
    required String message,
    required String goal,
    required List<Map<String, dynamic>> messages,
  }) {
    return <String, dynamic>{
      'toolName': toolName,
      'errorMessage': message,
      'goal': goal,
    };
  }

  Map<String, dynamic> _buildToolObservation({
    required String toolName,
    required AssistantToolResult result,
  }) {
    final data =
        (result.data as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    return <String, dynamic>{
      'toolName': toolName,
      'ok': result.success == true,
      'status': _deriveToolStatus(toolName: toolName, result: result),
      'errorCode': result.errorCode.name,
      'errorClass': _deriveErrorClass(result.errorCode.name),
      'retryable': _isRetryableError(result.errorCode.name),
      'message': result.message,
      'slotDelta': _extractSlotDelta(
        toolName: toolName,
        message: result.message,
        data: data,
      ),
      'data': data,
      'legacyMessage': result.message,
    };
  }

  String _deriveToolStatus({
    required String toolName,
    required AssistantToolResult result,
  }) {
    final rule = _reactPolicy.statusRuleFor(toolName);
    if (rule == null) return 'unknown';
    if (result.success) {
      final summary = (result.data?['summary'] as String?)?.trim() ?? '';
      return summary.isNotEmpty
          ? rule.successWithSummary
          : rule.successWithoutSummary;
    }
    if (result.errorCode == AssistantErrorCode.invalidArguments) {
      return rule.invalidArgumentsStatus;
    }
    if (result.errorCode == AssistantErrorCode.permissionDenied) {
      return rule.permissionDeniedStatus;
    }
    return rule.errorStatus;
  }

  String _deriveErrorClass(String codeName) {
    return _reactPolicy.errorClassMap[codeName] ?? 'tool_error';
  }

  bool _isRetryableError(String codeName) {
    return _reactPolicy.retryableErrorCodes.contains(codeName);
  }

  List<String> _extractPlannedSearchQueries(List<AssistantToolCall> toolCalls) {
    final out = <String>[];
    final seen = <String>{};
    for (final call in toolCalls) {
      if (!_isRetrievalLikeTool(call.name)) {
        continue;
      }
      final args = call.arguments;
      final direct = (args['query'] as String?)?.trim() ?? '';
      if (direct.isNotEmpty && seen.add(direct)) out.add(direct);
      final keyword = (args['keyword'] as String?)?.trim() ?? '';
      if (keyword.isNotEmpty && seen.add(keyword)) out.add(keyword);
      final keywords =
          (args['keywords'] as List?)
              ?.whereType<String>()
              .map((item) => item.trim())
              .where((item) => item.isNotEmpty)
              .toList(growable: false) ??
          const <String>[];
      for (final item in keywords) {
        if (seen.add(item)) out.add(item);
      }
    }
    return out;
  }

  bool _isRetrievalLikeTool(String toolName) {
    final registry = _toolMetadataRegistry;
    return registry?.isRetrievalLikeTool(toolName) ?? false;
  }

  _RuntimeExecutionShell _resolveExecutionShell(
    Map<String, dynamic> templateVariables,
  ) {
    final raw =
        (templateVariables['skillExecutionShell'] as Map?)
            ?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    return _RuntimeExecutionShell.fromMap(raw);
  }

  List<AssistantToolCall> _sanitizeToolCalls(
    List<AssistantToolCall> toolCalls, {
    required _RuntimeExecutionShell shell,
  }) {
    if (toolCalls.isEmpty) return toolCalls;
    final metadata = _toolMetadataRegistry;
    return toolCalls
        .map((call) {
          final args = _flattenToolArguments(call.arguments);
          if (!(metadata?.supportsQueryTasks(call.name) ?? false)) {
            return AssistantToolCall(
              name: call.name,
              arguments: args,
              id: call.id,
            );
          }
          final queryTasks = _buildSearchQueryTasks(args: args, shell: shell);
          if (queryTasks.length >= 2) {
            args['queryTasks'] = queryTasks;
            args.remove('queryVariants');
            final count = _RuntimeExecutionShell._positiveInt(
              args['count'],
              fallback: 5,
            );
            if (count > 4) {
              args['count'] = 4;
            }
          } else if (queryTasks.length == 1) {
            args['query'] = queryTasks.first['query'];
            args['queryTasks'] = queryTasks;
            args.remove('queryVariants');
          } else {
            args.remove('queryVariants');
            args.remove('queryTasks');
          }
          if (shell.providerPolicyType == ProviderPolicy.authorityFirst) {
            args.remove('provider');
            if (shell.authorityDomains.isNotEmpty) {
              args['authorityDomains'] = shell.authorityDomains;
            }
          } else if (shell.providerPolicyType == ProviderPolicy.preferredOnly &&
              shell.preferredProviders.isNotEmpty) {
            args['provider'] = shell.preferredProviders.first;
          }
          final freshness = args['freshnessHoursMax'];
          if (freshness is! num ||
              freshness.toInt() <= 0 ||
              freshness.toInt() > shell.freshnessHoursMax) {
            args['freshnessHoursMax'] = shell.freshnessHoursMax;
          }
          return AssistantToolCall(
            name: call.name,
            arguments: args,
            id: call.id,
          );
        })
        .toList(growable: false);
  }

  Map<String, dynamic> _flattenToolArguments(
    Map<String, dynamic> rawArguments,
  ) {
    final flattened = Map<String, dynamic>.from(rawArguments);

    void mergeNested(String key) {
      final nested = flattened.remove(key);
      if (nested is! Map) return;
      for (final entry in nested.entries) {
        final nestedKey = entry.key.toString().trim();
        if (nestedKey.isEmpty || flattened.containsKey(nestedKey)) continue;
        flattened[nestedKey] = entry.value;
      }
    }

    mergeNested('params');
    mergeNested('arguments');
    return flattened;
  }

  List<Map<String, dynamic>> _buildSearchQueryTasks({
    required Map<String, dynamic> args,
    required _RuntimeExecutionShell shell,
  }) {
    final taskBudget = shell.variantBudget <= 0 ? 1 : shell.variantBudget;
    final queryNormalization =
        (args['queryNormalization'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final commonTaskMetadata = <String, dynamic>{
      if (_RuntimeExecutionShell._stringList(
        queryNormalization['entityAnchors'],
      ).isNotEmpty)
        'entityAnchors': _RuntimeExecutionShell._stringList(
          queryNormalization['entityAnchors'],
        ),
      if (_RuntimeExecutionShell._stringList(
        queryNormalization['negativeKeywords'],
      ).isNotEmpty)
        'negativeKeywords': _RuntimeExecutionShell._stringList(
          queryNormalization['negativeKeywords'],
        ),
      if ((queryNormalization['answerShape'] as String?)?.trim().isNotEmpty ==
          true)
        'answerShape': (queryNormalization['answerShape'] as String).trim(),
      if ((queryNormalization['freshnessNeed'] as String?)?.trim().isNotEmpty ==
          true)
        'freshnessNeed': (queryNormalization['freshnessNeed'] as String).trim(),
    };
    final existingTasks = _coerceSearchTasks(args['queryTasks']);
    if (existingTasks.isNotEmpty) {
      return _normalizeSearchTasks(
        existingTasks,
        commonMetadata: commonTaskMetadata,
      ).take(taskBudget).toList(growable: false);
    }

    final directQuery = (args['query'] as String?)?.trim() ?? '';
    final queryVariants =
        (args['queryVariants'] as List?)
            ?.map((item) => item.toString().trim())
            .where((item) => item.isNotEmpty)
            .toList(growable: false) ??
        const <String>[];

    final tasks = <Map<String, dynamic>>[];
    final seen = <String>{};

    void addTask(String query, {String label = '', String dimension = ''}) {
      final normalizedQuery = query.trim().replaceAll(RegExp(r'\s+'), ' ');
      if (normalizedQuery.isEmpty || !seen.add(normalizedQuery)) return;
      tasks.add(<String, dynamic>{
        'query': normalizedQuery,
        'label': label.isNotEmpty ? label : _compactTaskLabel(normalizedQuery),
        if (dimension.isNotEmpty) 'dimension': dimension,
        ...commonTaskMetadata,
      });
    }

    if (directQuery.isNotEmpty) {
      addTask(directQuery);
    }
    for (final variant in queryVariants) {
      addTask(variant);
    }

    if (tasks.isEmpty) return const <Map<String, dynamic>>[];
    final limit = queryVariants.isNotEmpty ? taskBudget + 1 : taskBudget;
    return tasks.take(limit).toList(growable: false);
  }

  List<Map<String, dynamic>> _coerceSearchTasks(Object? raw) {
    if (raw is List) {
      return raw
          .whereType<Map>()
          .map((item) => item.cast<String, dynamic>())
          .toList(growable: false);
    }
    if (raw is Map) {
      return <Map<String, dynamic>>[raw.cast<String, dynamic>()];
    }
    final text = raw?.toString().trim() ?? '';
    if (text.isEmpty) return const <Map<String, dynamic>>[];
    if (text.startsWith('[') || text.startsWith('{')) {
      try {
        return _coerceSearchTasks(jsonDecode(text));
      } catch (_) {
        // Fall through to a single query task.
      }
    }
    return <Map<String, dynamic>>[
      <String, dynamic>{'query': text, 'label': _compactTaskLabel(text)},
    ];
  }

  List<Map<String, dynamic>> _normalizeSearchTasks(
    List<Map<String, dynamic>> tasks, {
    Map<String, dynamic> commonMetadata = const <String, dynamic>{},
  }) {
    final normalized = <Map<String, dynamic>>[];
    final seen = <String>{};
    for (final task in tasks) {
      final query = (task['query'] as String?)?.trim() ?? '';
      if (query.isEmpty || !seen.add(query)) continue;
      normalized.add(<String, dynamic>{
        ...commonMetadata,
        if ((task['id'] as String?)?.trim().isNotEmpty == true)
          'id': (task['id'] as String).trim(),
        'query': query,
        'label': (task['label'] as String?)?.trim().isNotEmpty == true
            ? (task['label'] as String).trim()
            : _compactTaskLabel(query),
        if ((task['dimension'] as String?)?.trim().isNotEmpty == true)
          'dimension': (task['dimension'] as String).trim(),
        if (_RuntimeExecutionShell._stringList(
          task['entityAnchors'],
        ).isNotEmpty)
          'entityAnchors': _RuntimeExecutionShell._stringList(
            task['entityAnchors'],
          ),
        if (_RuntimeExecutionShell._stringList(
          task['negativeKeywords'],
        ).isNotEmpty)
          'negativeKeywords': _RuntimeExecutionShell._stringList(
            task['negativeKeywords'],
          ),
        if ((task['answerShape'] as String?)?.trim().isNotEmpty == true)
          'answerShape': (task['answerShape'] as String).trim(),
        if ((task['freshnessNeed'] as String?)?.trim().isNotEmpty == true)
          'freshnessNeed': (task['freshnessNeed'] as String).trim(),
      });
    }
    return normalized;
  }

  String _compactTaskLabel(String query) {
    final normalized = query.trim().replaceAll(RegExp(r'\s+'), ' ');
    if (normalized.length <= 18) return normalized;
    return '${normalized.substring(0, 18)}...';
  }

  /// Extracts slot updates from tool output. This is a legitimate runtime
  /// responsibility (consuming structured tool data), not a model bypass.
  /// Slot extraction must come from tool metadata + structured payload only.
  Map<String, dynamic> _extractSlotDelta({
    required String toolName,
    required String message,
    required Map<String, dynamic> data,
  }) {
    final metadata = _toolMetadataRegistry;
    if (metadata == null) return const <String, dynamic>{};
    final slotOutputs = metadata.slotOutputsByToolName(toolName);
    if (slotOutputs.isEmpty) return const <String, dynamic>{};
    final delta = <String, dynamic>{};
    for (final slotOutput in slotOutputs) {
      final slotId = (slotOutput['slotId'] as String?)?.trim() ?? '';
      final path = (slotOutput['path'] as String?)?.trim() ?? '';
      if (slotId.isEmpty || path.isEmpty) continue;
      final value = _resolveStructuredPath(data, path);
      if (value is String) {
        final trimmed = value.trim();
        if (trimmed.isEmpty) continue;
        delta[slotId] = trimmed;
      } else if (value != null) {
        delta[slotId] = value;
      }
      final source = (slotOutput['source'] as String?)?.trim() ?? '';
      if (source.isNotEmpty && delta.containsKey(slotId)) {
        delta['source'] = source;
      }
    }
    return delta;
  }

  Object? _resolveStructuredPath(Map<String, dynamic> data, String path) {
    if (path.isEmpty) return null;
    Object? current = data;
    for (final segment in path.split('.')) {
      if (current is Map<String, dynamic>) {
        current = current[segment];
      } else if (current is Map) {
        current = current[segment];
      } else {
        return null;
      }
    }
    return current;
  }

  /// 从模型输出的 JSON 正文里解析 toolPlan / nextAction='tool_call' 字段，
  /// 用于不支持 native function calling 的模型（如 mimo-v2-flash）。
  List<AssistantToolCall> _extractToolCallsFromJsonText(String text) {
    if (text.trim().isEmpty) return const <AssistantToolCall>[];
    try {
      // 去掉 <think>...</think> 标签
      final stripped = text
          .replaceAll(
            RegExp(r'<think>[\s\S]*?</think>', caseSensitive: false),
            '',
          )
          .trim();
      // 找到第一个 JSON 对象
      final start = stripped.indexOf('{');
      if (start < 0) return const <AssistantToolCall>[];
      final decoded = jsonDecode(stripped.substring(start));
      if (decoded is! Map) return const <AssistantToolCall>[];
      final payload = decoded.cast<String, dynamic>();
      final turn = tryParseAssistantTurnOutput(payload);

      // 只在 nextAction='tool_call' 时才解析
      final nextAction =
          turn?.nextAction ??
          (((payload['decision'] as Map?)?['nextAction'] as String?)?.trim() ??
              '');
      if (nextAction != 'tool_call') return const <AssistantToolCall>[];

      final toolPlan = turn?.toolPlan ?? payload['toolPlan'];
      if (toolPlan is! List) return const <AssistantToolCall>[];

      final calls = <AssistantToolCall>[];
      for (final item in toolPlan) {
        if (item is! Map) continue;
        final toolName =
            (item['toolName'] as String? ?? item['name'] as String?)?.trim() ??
            '';
        if (toolName.isEmpty) continue;
        final rawArgs = item['arguments'];
        final args = rawArgs is Map
            ? rawArgs.cast<String, dynamic>()
            : <String, dynamic>{
                for (final entry in item.entries)
                  if (entry.key != 'toolName' &&
                      entry.key != 'name' &&
                      entry.key != 'toolCallId')
                    '${entry.key}': entry.value,
              };
        calls.add(AssistantToolCall(name: toolName, arguments: args));
      }

      return calls;
    } catch (_) {
      return const <AssistantToolCall>[];
    }
  }

  /// Determines the user-facing phase based on current state.
  String _determineUserPhase(ReactRunState state) {
    if (state.iteration == 1 && state.evidences.isEmpty) {
      return 'understanding';
    }
    if (state.evidences.isNotEmpty) {
      return 'analyzing';
    }
    return 'understanding';
  }

  /// Builds a phase hint system message from config + tool metadata prompts.
  String _buildPhaseHint(String phase, List<String> toolNames) {
    final phases = _phaseHintsConfig['phases'] as Map?;
    final phaseConfig = (phases?[phase] as Map?)?.cast<String, dynamic>();
    final baseHint = (phaseConfig?['systemHint'] as String?) ?? '';
    const userFacingNarrativeHint =
        '过程说明只用用户能听懂的话，重点解释为什么现在这样做、这一步能帮用户减少什么不确定性、信息是否已经够答。'
        '语气要像贴身助手，简洁、自然、有陪伴感，不要输出内部步骤编号、协议字段名或生硬的系统状态播报。';
    final effectiveBaseHint = baseHint.isEmpty
        ? userFacingNarrativeHint
        : '$baseHint\n\n$userFacingNarrativeHint';

    if (phase == 'understanding' || phase == 'analyzing') {
      final toolHints = <String>[];
      final registry = _toolMetadataRegistry;
      if (registry != null) {
        for (final name in toolNames) {
          final hint = registry.promptHintForTool(name);
          if (hint != null && hint.isNotEmpty) {
            toolHints.add('- $name: $hint');
          }
        }
      }
      if (toolHints.isEmpty) return effectiveBaseHint;
      final prefix = (_phaseHintsConfig['toolHintPrefix'] as String?) ?? '';
      final suffix = (_phaseHintsConfig['toolHintSuffix'] as String?) ?? '';
      return '$effectiveBaseHint\n\n$prefix${toolHints.join('\n')}$suffix';
    }
    return effectiveBaseHint;
  }

  Future<void> _ensurePhaseHintsLoaded() async {
    _phaseHintsLoading ??= () async {
      try {
        final raw = await rootBundle.loadString(_phaseHintsPath);
        final decoded = jsonDecode(raw);
        if (decoded is Map) {
          _phaseHintsConfig = decoded.cast<String, dynamic>();
        }
      } catch (_) {
        _phaseHintsConfig = const <String, dynamic>{};
      }
    }();
    await _phaseHintsLoading;
  }

  Future<void> _ensureReactPolicyLoaded() async {
    _reactPolicyLoading ??= () async {
      _reactPolicy = await ReactPolicy.loadFromAsset(_reactPolicyPath);
    }();
    await _reactPolicyLoading;
  }

  String _extractThinkingTextFromJson(String text) {
    try {
      final decoded = jsonDecode(text);
      if (decoded is Map) {
        final payload = decoded.cast<String, dynamic>();
        final turn = tryParseAssistantTurnOutput(payload);
        final rs = turn?.reasonShort.trim() ?? '';
        if (rs.isNotEmpty) return rs;
        final um =
            turn?.userMarkdown.trim() ??
            (payload['userMarkdown'] as String?)?.trim() ??
            '';
        if (um.isNotEmpty && !um.startsWith('{') && um.length > 20) {
          return um;
        }
      }
    } catch (_) {}
    return '';
  }

  /// Extract user-visible reasoning from the LLM output, combining canonical
  /// `reasonShort`, reasoning text, and cleaned raw output.
  String _extractBestThinking(String outputText, String reasoningText) {
    final fromJson = _extractThinkingTextFromJson(outputText);
    if (fromJson.isNotEmpty) return fromJson;
    final cleaned = _cleanReasoningForDisplay(reasoningText);
    if (cleaned.isNotEmpty) return cleaned;
    if (outputText.trim().isNotEmpty) {
      final fromOutput = _extractThinkingTextFromJson(
        outputText.trim().startsWith('{') ? outputText : reasoningText,
      );
      if (fromOutput.isNotEmpty) return fromOutput;
    }
    return '';
  }

  static final _jsonKeyPattern = RegExp(
    r'"(?:contractVersion|decision|nextAction|toolPlan|slotState|messageKind|tool_calls)',
  );

  String _cleanReasoningForDisplay(String reasoning) {
    final text = reasoning.trim();
    if (text.isEmpty || text.length < 10) return '';
    if (text.startsWith('{') && _jsonKeyPattern.hasMatch(text)) return '';
    final cleaned = text
        .replaceAll(RegExp(r'<think>|</think>', multiLine: true), '')
        .replaceAll(RegExp(r'```json[\s\S]*?```', multiLine: true), '')
        .trim();
    if (cleaned.isEmpty || cleaned.length < 10) return '';
    if (cleaned.startsWith('{') && cleaned.endsWith('}')) return '';
    return cleaned;
  }
}

class _RuntimeExecutionShell {
  const _RuntimeExecutionShell({
    required this.toolBudget,
    required this.variantBudget,
    required this.reflectionBudget,
    required this.problemClass,
    required this.providerPolicy,
    required this.preferredProviders,
    required this.authorityDomains,
    required this.freshnessHoursMax,
  });

  final int toolBudget;
  final int variantBudget;
  final int reflectionBudget;
  final String problemClass;
  final String providerPolicy;
  final List<String> preferredProviders;
  final List<String> authorityDomains;
  final int freshnessHoursMax;

  ProviderPolicy get providerPolicyType => parseProviderPolicy(providerPolicy);

  factory _RuntimeExecutionShell.fromMap(Map<String, dynamic> map) {
    return _RuntimeExecutionShell(
      toolBudget: _positiveInt(map['toolBudget'], fallback: 12),
      variantBudget: _nonNegativeInt(map['variantBudget'], fallback: 2),
      reflectionBudget: _nonNegativeInt(map['reflectionBudget'], fallback: 2),
      problemClass: (map['problemClass'] as String?)?.trim() ?? '',
      providerPolicy:
          (map['providerPolicy'] as String?)?.trim().isNotEmpty == true
          ? (map['providerPolicy'] as String).trim()
          : ProviderPolicy.inherit.wireName,
      preferredProviders: _stringList(map['preferredProviders']),
      authorityDomains: _stringList(map['authorityDomains']),
      freshnessHoursMax: _positiveInt(map['freshnessHoursMax'], fallback: 72),
    );
  }

  static int _positiveInt(Object? value, {required int fallback}) {
    if (value is num && value.toInt() > 0) return value.toInt();
    final parsed = int.tryParse(value?.toString() ?? '');
    if (parsed != null && parsed > 0) return parsed;
    return fallback;
  }

  static int _nonNegativeInt(Object? value, {required int fallback}) {
    if (value is num && value.toInt() >= 0) return value.toInt();
    final parsed = int.tryParse(value?.toString() ?? '');
    if (parsed != null && parsed >= 0) return parsed;
    return fallback;
  }

  static List<String> _stringList(Object? value) {
    if (value is List) {
      return value
          .map((item) => item.toString().trim())
          .where((item) => item.isNotEmpty)
          .toList(growable: false);
    }
    return const <String>[];
  }
}
