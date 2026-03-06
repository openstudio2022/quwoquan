import 'dart:convert';

import 'package:flutter/services.dart' show rootBundle;
import 'package:quwoquan_app/personal_assistant/contracts/runtime_policies.dart';
import 'package:quwoquan_app/personal_assistant/engine/llm_provider.dart';
import 'package:quwoquan_app/personal_assistant/engine/react_planner.dart';
import 'package:quwoquan_app/personal_assistant/engine/react_state.dart';
import 'package:quwoquan_app/personal_assistant/engine/tool_result_assessor.dart';
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
       _assessor = ToolResultAssessor();

  final AssistantLlmProvider _llmProvider;
  final AssistantToolRegistry _toolRegistry;
  final ReactPlanner _planner;
  final ReactReflector _reflector;
  final ToolMetadataRegistry? _toolMetadataRegistry;
  final ToolResultAssessor _assessor;
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
    if (provider is! OpenAiCompatibleLlmProvider) return '';
    return provider.reasonStream(
      messages: messages,
      availableTools: const <String>[],
      onDelta: (delta) {
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
      },
      templateContext: templateContext,
      templateVariables: templateVariables,
      templateId: templateId,
      templateVersion: templateVersion,
      sessionId: sessionId,
      runId: runId ?? '',
      traceId: traceId ?? '',
    );
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
    final goalText = goal.isEmpty
        ? (messages.lastWhere(
                (m) => m['role'] == 'user',
                orElse: () => const <String, String>{'content': ''},
              )['content'] ??
              '')
        : goal;
    final state = ReactRunState(
      goal: goalText,
      maxIterations: maxIterations,
      toolBudget: maxIterations * 2,
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
        messages.add(<String, String>{
          'role': 'system',
          'content': phaseHint,
        });
      }

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
        onDelta: onDelta != null
            ? (delta) {
                onDelta(delta);
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
                    },
                  ),
                );
              }
            : null,
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
          },
        ),
      );
      // 当模型不走 native function calling（如 mimo-v2-flash），尝试从 JSON 正文
      // 的 toolPlan / nextAction='tool_call' 字段里解析工具调用。
      // 合成阶段（availableToolNames 为空）不解析 JSON 工具调用，
      // 防止模型输出 nextAction='tool_call' 时误触发工具执行。
      final effectiveToolCalls = output.hasToolCalls
          ? output.toolCalls
          : (availableToolNames.isEmpty
              ? const <AssistantToolCall>[]
              : _extractToolCallsFromJsonText(output.text));
      // Track consecutive empty iterations for deadlock detection
      final isEmptyOutput = output.text.trim().isEmpty && effectiveToolCalls.isEmpty;
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
              'userMessage': '遇到困难，基于已有信息为您回答',
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
        messages.add(<String, dynamic>{
          'role': rawMsg['role'] ?? 'assistant',
          if (rawMsg['content'] != null) 'content': rawMsg['content'],
          'tool_calls': rawMsg['tool_calls'],
        }.map((k, v) => MapEntry(k, v)));
      } else {
        // JSON 解析路径：为每个工具调用生成一个带 id 的 tool_calls 列表
        final syntheticToolCalls = effectiveToolCalls.map((call) {
          final callId = call.id.isNotEmpty ? call.id : 'call_${call.name}_${state.iteration}';
          return <String, dynamic>{
            'id': callId,
            'type': 'function',
            'function': <String, dynamic>{
              'name': call.name,
              'arguments': jsonEncode(call.arguments),
            },
          };
        }).toList(growable: false);
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
        state.usedTools += 1;
        if (step.toolName.contains('search')) {
          final query = (step.arguments['query'] ?? step.arguments['keyword'] ?? '').toString();
          pushTrace(
            AssistantTraceEvent(
              type: AssistantTraceEventType.searchStarted,
              message: query.isNotEmpty ? '检索: $query' : '开始检索',
              timestamp: DateTime.now(),
              runId: runId,
              traceId: traceId,
              toolCallId: step.id,
              data: <String, dynamic>{
                'tool': step.toolName,
                'query': query,
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
        final shouldSuppressToolErrorForUser =
            !isOk &&
            _shouldSuppressToolErrorForUser(step.toolName, result);
        state.evidences.add(<String, dynamic>{
          'stepId': step.id,
          'tool': step.toolName,
          'success': result.success,
          'message': result.message,
          'data': result.data,
        });
        final traceData = <String, dynamic>{
          ...?result.data,
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
        if (step.toolName.contains('search') && isOk) {
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
                'tool': step.toolName,
                'referenceCount': refs,
                'qualityScore': (result.data?['qualityScore'] as num?)?.toDouble() ?? 0.0,
              },
            ),
          );
        }
        final toolObservation = _buildToolObservation(
          toolName: step.toolName,
          result: result,
        );
        // OpenAI 协议要求：tool message 必须有 tool_call_id，对应 assistant message 里的 tool_calls[].id
        final effectiveCallId = step.toolCallId.isNotEmpty
            ? step.toolCallId
            : 'call_${step.toolName}_${state.iteration}';
        messages.add(<String, dynamic>{
          'role': 'tool',
          'tool_call_id': effectiveCallId,
          'content': jsonEncode(toolObservation),
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
                '请结合历史对话决定下一步：'
                '若是天气问题且缺少城市，请追问城市；若城市已知，优先给出可执行的降级建议并说明可重试。',
          });
        }
        // Layer 3 反思循环：当 web_search 质量评分不足时，注入反思提示驱动 LLM 重写查询
        if (step.toolName == 'web_search' && isOk) {
          final data = (result.data as Map?)?.cast<String, dynamic>() ?? const <String, dynamic>{};
          final qualityScore = (data['qualityScore'] as num?)?.toDouble() ?? 0.0;
          final reflectionRound = state.openQuestions
              .where((q) => q.startsWith('reflect_round:'))
              .length;
          if (qualityScore < _reactPolicy.reflectionQualityScoreMin &&
              reflectionRound < _reactPolicy.reflectionMaxRounds) {
            final roundLabel = 'reflect_round:${reflectionRound + 1}';
            state.openQuestions.add(roundLabel);
            final authorityDomains = (data['authorityDomains'] as List?)?.cast<String>() ?? <String>[];
            final refs = (data['references'] as List?)?.cast<Map<String, dynamic>>() ?? <Map<String, dynamic>>[];
            final snippets = refs.take(3).map((r) => r['snippet'] ?? r['title'] ?? '').where((s) => s.isNotEmpty).toList();
            messages.add(<String, String>{
              'role': 'system',
              'content': '本轮搜索质量评分过低（qualityScore=${qualityScore.toStringAsFixed(2)}），'
                  '请诊断失败原因并生成3条差异化重写查询词：\n'
                  '失败信息: ${result.message}\n'
                  '目标权威域: ${authorityDomains.join(", ")}\n'
                  '已检索片段摘要: ${snippets.join(" | ")}\n'
                  '这是第 ${reflectionRound + 1} 次反思（最多${_reactPolicy.reflectionMaxRounds}次）。'
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

        final replan = _reflector.shouldReplan(
          state: state,
          lastStepSuccess: isOk,
          lastObservation: toolObservation,
          policy: _reactPolicy,
        );

        // Post-tool assessment: emit user-visible evaluation
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
            },
          ),
        );

        if (replan) {
          state.openQuestions.add('step ${step.id} result needs re-check');
          pushTrace(
            AssistantTraceEvent(
              type: AssistantTraceEventType.replanTriggered,
              message: assessment.userMessage,
              timestamp: DateTime.now(),
              runId: runId,
              traceId: traceId,
              data: <String, dynamic>{
                'reason': assessment.type.name,
              },
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
        (e) => e.type == AssistantTraceEventType.assistantDelta &&
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
      final name = call.name.trim().toLowerCase();
      if (!(name.contains('search') || name.contains('retrieval'))) {
        continue;
      }
      final args = call.arguments;
      final direct = (args['query'] as String?)?.trim() ?? '';
      if (direct.isNotEmpty && seen.add(direct)) out.add(direct);
      final keyword = (args['keyword'] as String?)?.trim() ?? '';
      if (keyword.isNotEmpty && seen.add(keyword)) out.add(keyword);
      final keywords = (args['keywords'] as List?)
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

  Map<String, dynamic> _extractSlotDelta({
    required String toolName,
    required String message,
    required Map<String, dynamic> data,
  }) {
    if (toolName != 'local_context') return const <String, dynamic>{};
    final cityFromData = (data['city'] as String?)?.trim() ?? '';
    if (cityFromData.isNotEmpty) {
      return <String, dynamic>{'city': cityFromData, 'source': 'tool_data'};
    }
    final cityMatch = RegExp(
      r'city=([\u4e00-\u9fa5A-Za-z]{2,16})',
    ).firstMatch(message);
    final cityFromMessage = (cityMatch?.group(1) ?? '').trim();
    if (cityFromMessage.isNotEmpty) {
      return <String, dynamic>{
        'city': cityFromMessage,
        'source': 'tool_message',
      };
    }
    return const <String, dynamic>{};
  }

  /// 从模型输出的 JSON 正文里解析 toolPlan / nextAction='tool_call' 字段，
  /// 用于不支持 native function calling 的模型（如 mimo-v2-flash）。
  List<AssistantToolCall> _extractToolCallsFromJsonText(String text) {
    if (text.trim().isEmpty) return const <AssistantToolCall>[];
    try {
      // 去掉 <think>...</think> 标签
      final stripped = text
          .replaceAll(RegExp(r'<think>[\s\S]*?</think>', caseSensitive: false), '')
          .trim();
      // 找到第一个 JSON 对象
      final start = stripped.indexOf('{');
      if (start < 0) return const <AssistantToolCall>[];
      final decoded = jsonDecode(stripped.substring(start));
      if (decoded is! Map) return const <AssistantToolCall>[];

      // 只在 nextAction='tool_call' 时才解析
      final decision = decoded['decision'];
      String nextAction = '';
      if (decision is Map) {
        nextAction = (decision['nextAction'] as String?)?.trim() ?? '';
      }
      if (nextAction != 'tool_call') return const <AssistantToolCall>[];

      final toolPlan = decoded['toolPlan'];
      if (toolPlan == null) return const <AssistantToolCall>[];

      final calls = <AssistantToolCall>[];

      if (toolPlan is Map) {
        // 格式一：{"toolPlan": {"web_search": {...args}}}
        toolPlan.forEach((key, value) {
          final toolName = (key as String?)?.trim() ?? '';
          if (toolName.isEmpty) return;
          final args = value is Map
              ? value.cast<String, dynamic>()
              : <String, dynamic>{};
          calls.add(AssistantToolCall(name: toolName, arguments: args));
        });
      } else if (toolPlan is List) {
        // 格式二：{"toolPlan": [{"tool": "web_search", ...args}]}
        for (final item in toolPlan) {
          if (item is! Map) continue;
          final toolName =
              (item['tool'] as String? ?? item['toolName'] as String?)
                  ?.trim() ??
              '';
          if (toolName.isEmpty) continue;
          final args = <String, dynamic>{};
          item.forEach((k, v) {
            if (k != 'tool' && k != 'toolName') {
              args['$k'] = v;
            }
          });
          calls.add(AssistantToolCall(name: toolName, arguments: args));
        }
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
      if (toolHints.isEmpty) return baseHint;
      final prefix = (_phaseHintsConfig['toolHintPrefix'] as String?) ?? '';
      final suffix = (_phaseHintsConfig['toolHintSuffix'] as String?) ?? '';
      return '$baseHint\n\n$prefix${toolHints.join('\n')}$suffix';
    }
    return baseHint;
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
}

