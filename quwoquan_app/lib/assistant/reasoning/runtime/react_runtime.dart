import 'dart:convert';

import 'package:flutter/services.dart' show rootBundle;
import 'package:quwoquan_app/assistant/contracts/answer_boundary_policy.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_turn_contract.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_policies.dart';
import 'package:quwoquan_app/assistant/infrastructure/assistant_model_runtime.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_display_text_resolver.dart';
import 'package:quwoquan_app/assistant/reasoning/planner/react_planner.dart';
import 'package:quwoquan_app/assistant/reasoning/runtime/react_state.dart';
import 'package:quwoquan_app/assistant/reasoning/runtime/tool_execution_guard.dart';
import 'package:quwoquan_app/assistant/reasoning/runtime/tool_result_assessor.dart';
import 'package:quwoquan_app/assistant/reasoning/runtime/tool_result_truncator.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/assistant/tool/runtime/tool_metadata_registry.dart';
import 'package:quwoquan_app/assistant/tool/runtime/tool_registry.dart';
import 'package:quwoquan_app/assistant/tool/schema/tool_schema.dart';

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
         permissionResolver: toolMetadataRegistry != null
             ? (name) {
                 final c = toolMetadataRegistry.permissionForTool(name);
                 return c != null
                     ? ToolPermission(
                         requireConfirmation: c.requireConfirmation,
                         allowedSchemes: c.allowedSchemes,
                       )
                     : null;
               }
             : null,
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
      'assets/assistant/config/react_policy.json';
  static const String _phaseHintsPath =
      'assets/assistant/config/user_phase_hints.json';
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
    _assessor.boundaryPolicy = _resolveAnswerBoundaryPolicy(templateVariables);
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
      final availableToolNames = state.forceAnswerOnly
          ? const <String>[]
          : (availableToolNamesOverride ?? listAvailableToolNames());
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
      final currentPhase = _determineUserPhase(
        state,
        availableToolNames,
        templateId: templateId,
        hasPrecomputedSearch: executionShell.preComputedQueryTasks.isNotEmpty,
      );
      final phaseHint = _buildPhaseHint(currentPhase, availableToolNames);
      if (phaseHint.isNotEmpty) {
        messages.add(<String, String>{'role': 'system', 'content': phaseHint});
      }

      pushTrace(
        AssistantTraceEvent(
          type: AssistantTraceEventType.thinkingProgress,
          message: _seedThinkingProgressMessage(currentPhase, state.goal),
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
      final wrappedOnDelta = onDelta != null
          ? (String delta) {
              if (delta.trim().isEmpty) return;
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
      final contextEnvelope = _templateMapVariable(
        templateVariables,
        'contextEnvelope',
      );
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
            if (output.reasoningText.trim().isNotEmpty)
              'providerReasoningContinuation': output.reasoningText.trim(),
            if (output.usageEntries.isNotEmpty)
              'usageEntries': output.usageEntries,
          },
        ),
      );
      final extractedThinking = _extractBestThinking(
        output.text,
        output.reasoningText,
        currentPhase: currentPhase,
      );
      if (extractedThinking.isNotEmpty) {
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
        availableToolNames: availableToolNames,
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
            if (output.reasoningText.trim().isNotEmpty)
              'provider_reasoning_continuation': output.reasoningText.trim(),
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
          if (output.reasoningText.trim().isNotEmpty)
            'provider_reasoning_continuation': output.reasoningText.trim(),
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
        final toolKind = _toolKind(step.toolName);
        if (toolKind != 'context') {
          state.usedTools += 1;
        }
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
          if (toolKind.isNotEmpty) 'toolKind': toolKind,
          'problemClass': executionShell.problemClass,
          'retrievalLike': retrievalLike,
          if ((result.data?['references'] as List?) != null)
            'referenceCount': (result.data?['references'] as List).length,
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
                'references':
                    (result.data?['references'] as List?) ?? const <dynamic>[],
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
        final truncatedContent = _resultTruncator.truncateJson(toolObservation);
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
          if (retrievalLike) {
            messages.add(const <String, String>{
              'role': 'system',
              'content':
                  '本轮外部检索能力暂不可用。若当前证据仍不足，请不要编造确定性答案。优先给出稳态降级答复，并明确说明无法拿到最新外部信息与是否值得稍后重试。',
            });
          } else if (toolKind == 'context') {
            messages.add(const <String, String>{
              'role': 'system',
              'content':
                  '本地上下文暂不可用，但这不等于外部检索不可用。优先利用用户已明确提供的信息继续检索或判断；只有在关键地点或设备信息仍缺失时，才改为 ask_user 澄清。',
            });
          }
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
              'assessment': assessment.toJson(),
              'assessmentType': assessment.assessmentType.wireName,
              'userMessage': assessment.userMessage,
              'shouldContinueLoop': assessment.shouldContinueLoop,
              'isAssessment': true,
              'allowAnswerWithCurrentEvidence':
                  assessment.allowAnswerWithCurrentEvidence,
              'reasonCode': assessment.reasonCode.wireName,
              'referenceCount': assessment.referenceCount,
              'queryCount': assessment.queryCount,
              if (result.data?['queryLabels'] is List)
                'queryLabels': result.data?['queryLabels'],
              'coveredDimensions': assessment.coveredDimensions,
              'missingDimensions': assessment.missingDimensions,
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
              visibility: TraceVisibility.internal,
              data: <String, dynamic>{
                'reason': assessment.reasonCode.wireName,
                'assessment': assessment.toJson(),
              },
            ),
          );
          break;
        }
        if (!assessment.shouldContinueLoop) {
          state.forceAnswerOnly = true;
          messages.add(<String, String>{
            'role': 'system',
            'content': assessment.allowAnswerWithCurrentEvidence
                ? '当前已经拿到足够支持回答的证据。不要继续调用任何工具，直接基于已有证据输出最终 answer；如果仍有不确定点，请用 bounded answer 明确说明边界。'
                : '当前步骤已经足够进入成答。不要继续调用任何工具，直接输出最终 answer。',
          });
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
    if (rule.messageKeywords.isEmpty) return true;
    final lowered = result.message.toLowerCase();
    for (final keyword in rule.messageKeywords) {
      final token = keyword.trim().toLowerCase();
      if (token.isNotEmpty && lowered.contains(token)) {
        return true;
      }
    }
    return false;
  }

  AnswerBoundaryPolicy _resolveAnswerBoundaryPolicy(
    Map<String, dynamic> templateVariables,
  ) {
    final raw =
        (templateVariables['answerBoundaryPolicy'] as Map?)
            ?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    if (raw.isEmpty) {
      return const AnswerBoundaryPolicy();
    }
    try {
      return AnswerBoundaryPolicy.fromJson(raw);
    } catch (_) {
      return const AnswerBoundaryPolicy();
    }
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

  String _toolKind(String toolName) {
    final registry = _toolMetadataRegistry;
    return registry?.toolKindByName(toolName) ?? '';
  }

  _RuntimeExecutionShell _resolveExecutionShell(
    Map<String, dynamic> templateVariables,
  ) {
    final raw = _templateMapVariable(templateVariables, 'skillExecutionShell');
    return _RuntimeExecutionShell.fromMap(raw);
  }

  Map<String, dynamic> _templateMapVariable(
    Map<String, dynamic> templateVariables,
    String key,
  ) {
    final raw = templateVariables[key];
    if (raw is Map) {
      return raw.cast<String, dynamic>();
    }
    if (raw is String) {
      final text = raw.trim();
      if (text.isEmpty) return const <String, dynamic>{};
      try {
        final decoded = jsonDecode(text);
        if (decoded is Map) {
          return decoded.cast<String, dynamic>();
        }
      } catch (_) {
        return const <String, dynamic>{};
      }
    }
    return const <String, dynamic>{};
  }

  List<AssistantToolCall> _sanitizeToolCalls(
    List<AssistantToolCall> toolCalls, {
    required _RuntimeExecutionShell shell,
    required List<String> availableToolNames,
  }) {
    final metadata = _toolMetadataRegistry;
    final sanitized = toolCalls
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
          if (queryTasks.isNotEmpty) {
            args['queryTasks'] = queryTasks;
            final count = _RuntimeExecutionShell._positiveInt(
              args['count'],
              fallback: 5,
            );
            if (count > 4) {
              args['count'] = 4;
            }
          } else {
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
        .toList(growable: true);
    final hasRetrievalCall = sanitized.any(
      (call) => _isRetrievalLikeTool(call.name),
    );
    final hasContextCall = sanitized.any(
      (call) => _toolKind(call.name) == 'context',
    );
    final shouldAutoInjectRetrieval =
        !hasRetrievalCall &&
        shell.preComputedQueryTasks.isNotEmpty &&
        availableToolNames.contains('web_search') &&
        (sanitized.isEmpty || hasContextCall);
    if (shouldAutoInjectRetrieval) {
      final queryTasks = _buildSearchQueryTasks(
        args: const <String, dynamic>{},
        shell: shell,
      );
      if (queryTasks.isNotEmpty) {
        final firstQuery = (queryTasks.first['query'] as String?)?.trim() ?? '';
        if (firstQuery.isNotEmpty) {
          sanitized.add(
            AssistantToolCall(
              name: 'web_search',
              arguments: <String, dynamic>{
                'query': firstQuery,
                'queryTasks': queryTasks,
              },
              id: hasContextCall
                  ? 'auto_web_search_after_context'
                  : 'auto_web_search_from_precomputed_tasks',
            ),
          );
        }
      }
    }
    return sanitized;
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
      final taskBudget = _queryTaskBudget(
        availableCount: existingTasks.length,
        shell: shell,
      );
      return _normalizeSearchTasks(
        existingTasks,
        commonMetadata: commonTaskMetadata,
      ).take(taskBudget).toList(growable: false);
    }
    if (shell.preComputedQueryTasks.isNotEmpty) {
      final taskBudget = _queryTaskBudget(
        availableCount: shell.preComputedQueryTasks.length,
        shell: shell,
      );
      return _normalizeSearchTasks(
        shell.preComputedQueryTasks,
        commonMetadata: commonTaskMetadata,
      ).take(taskBudget).toList(growable: false);
    }
    return const <Map<String, dynamic>>[];
  }

  int _queryTaskBudget({
    required int availableCount,
    required _RuntimeExecutionShell shell,
  }) {
    if (availableCount <= 0) {
      return 0;
    }
    final configuredBudget = shell.variantBudget > 0 ? shell.variantBudget : 4;
    return configuredBudget < availableCount ? configuredBudget : availableCount;
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
        return const <Map<String, dynamic>>[];
      }
    }
    return const <Map<String, dynamic>>[];
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
  String _determineUserPhase(
    ReactRunState state,
    List<String> availableToolNames, {
    required String templateId,
    required bool hasPrecomputedSearch,
  }) {
    final normalizedTemplateId = templateId.trim();
    final answeringTemplate =
        normalizedTemplateId == 'synthesizer.final_answer' ||
        normalizedTemplateId == 'phase_one_direct_answer';
    if (state.forceAnswerOnly || answeringTemplate) {
      return 'answering';
    }
    if (hasPrecomputedSearch && state.iteration == 1 && state.usedTools == 0) {
      return 'search';
    }
    if (state.iteration == 1 &&
        state.evidences.isEmpty &&
        state.usedTools == 0) {
      return 'understanding';
    }
    if (state.evidences.isNotEmpty || state.usedTools > 0) {
      return 'search';
    }
    if (state.iteration > 1 && availableToolNames.isNotEmpty) {
      return 'search';
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

    if (phase == 'understanding') {
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

  String _extractThinkingTextFromJson(String text, {String currentPhase = ''}) {
    try {
      final decoded = jsonDecode(text);
      if (decoded is Map) {
        final payload = decoded.cast<String, dynamic>();
        final turn = tryParseAssistantTurnOutput(payload);
        final rs = turn?.reasonShort.trim() ?? '';
        if (rs.isNotEmpty) {
          return _normalizeStructuredThinking(
            raw: rs,
            currentPhase: currentPhase,
            turn: turn,
          );
        }
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
  String _extractBestThinking(
    String outputText,
    String reasoningText, {
    required String currentPhase,
  }) {
    final fromJson = _extractThinkingTextFromJson(
      outputText,
      currentPhase: currentPhase,
    );
    if (fromJson.isNotEmpty) return fromJson;
    final fromReasoningJson = _extractThinkingTextFromJson(
      reasoningText,
      currentPhase: currentPhase,
    );
    if (fromReasoningJson.isNotEmpty) return fromReasoningJson;
    return '';
  }

  String _normalizeStructuredThinking({
    required String raw,
    required String currentPhase,
    AssistantTurnOutput? turn,
  }) {
    final text = raw.trim();
    if (text.isEmpty) return '';
    final intentSummary =
        turn?.understandingSnapshot.intentSummary.trim() ?? '';
    final userGoal = turn?.intentGraph?.userGoal.trim() ?? '';
    final topic = _normalizeThinkingTopic(
      intentSummary.isNotEmpty ? intentSummary : userGoal,
    );
    final internalNarration =
        AssistantDisplayTextResolver.containsInternalPlannerNarrationFragment(
          text,
        );
    final needsTopicEnrichment =
        topic.isNotEmpty &&
        !text.contains(topic) &&
        _looksLikeGenericThinkingText(text);
    if (!internalNarration && !needsTopicEnrichment) {
      return text;
    }
    switch (currentPhase) {
      case 'understanding':
        if (topic.isNotEmpty) {
          return '我先确认你想知道的重点是$topic，再核对最新信息。';
        }
        return '我先确认你最关心的重点，再核对最新信息。';
      case 'search':
        if (topic.isNotEmpty) {
          return '我先把和$topic最相关的几路信息拆开核对。';
        }
        return '我先把最影响结论的几路信息拆开核对。';
      case 'answering':
        if (topic.isNotEmpty) {
          return '我已经把$topic的关键信息核对好了，开始整理结论。';
        }
        return '我已经把关键信息核对好了，开始整理结论。';
      default:
        return text;
    }
  }

  String _normalizeThinkingTopic(String raw) {
    var topic = raw.trim();
    if (topic.isEmpty) return '';
    topic = topic
        .replaceFirst(RegExp(r'^(用户)?(?:想|要)?(?:了解|知道|确认|判断|查询)'), '')
        .replaceFirst(RegExp(r'^(一下|当前|现在|一下子)'), '')
        .trim();
    return topic;
  }

  String _seedThinkingProgressMessage(String currentPhase, String goal) {
    final topic = _normalizeThinkingTopic(goal);
    switch (currentPhase) {
      case 'understanding':
        if (topic.isNotEmpty) {
          return '我先确认你想知道的重点是$topic。';
        }
        return '我先确认你最关心的重点。';
      case 'answering':
        if (topic.isNotEmpty) {
          return '我开始整理$topic的关键信息。';
        }
        return '我开始整理已经核对好的关键信息。';
      case 'search':
        if (topic.isNotEmpty) {
          return '我先把和$topic最相关的几路信息拆开核对。';
        }
        return '我先把最影响结论的几路信息拆开核对。';
      default:
        return '理解问题中';
    }
  }

  bool _looksLikeGenericThinkingText(String text) {
    final normalized = text.trim();
    if (normalized.isEmpty) return false;
    if (normalized.runes.length <= 16) return true;
    return RegExp(
      r'(问题焦点|组织执行|开始处理|开始整理|聚焦问题主线|进入理解阶段|进入检索准备|进入回答阶段)',
    ).hasMatch(normalized);
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
    this.preComputedQueryTasks = const [],
  });

  final int toolBudget;
  final int variantBudget;
  final int reflectionBudget;
  final String problemClass;
  final String providerPolicy;
  final List<String> preferredProviders;
  final List<String> authorityDomains;
  final int freshnessHoursMax;
  final List<Map<String, dynamic>> preComputedQueryTasks;

  ProviderPolicy get providerPolicyType => parseProviderPolicy(providerPolicy);

  factory _RuntimeExecutionShell.fromMap(Map<String, dynamic> map) {
    final rawTasks = map['preComputedQueryTasks'];
    final tasks = rawTasks is List
        ? rawTasks
              .whereType<Map>()
              .map((item) => item.cast<String, dynamic>())
              .toList(growable: false)
        : const <Map<String, dynamic>>[];
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
      preComputedQueryTasks: tasks,
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
