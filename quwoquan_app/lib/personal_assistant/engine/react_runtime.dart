import 'package:quwoquan_app/personal_assistant/engine/llm_provider.dart';
import 'package:quwoquan_app/personal_assistant/engine/react_planner.dart';
import 'package:quwoquan_app/personal_assistant/engine/react_state.dart';
import 'package:quwoquan_app/personal_assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/personal_assistant/tools/tool_registry.dart';

class ReactRuntimeResult {
  const ReactRuntimeResult({required this.finalText, required this.traces});

  final String finalText;
  final List<AssistantTraceEvent> traces;
}

class ReactRuntime {
  ReactRuntime({
    required AssistantLlmProvider llmProvider,
    required AssistantToolRegistry toolRegistry,
    ReactPlanner? planner,
    ReactReflector? reflector,
  }) : _llmProvider = llmProvider,
       _toolRegistry = toolRegistry,
       _planner = planner ?? const ReactPlanner(),
       _reflector = reflector ?? const ReactReflector();

  final AssistantLlmProvider _llmProvider;
  final AssistantToolRegistry _toolRegistry;
  final ReactPlanner _planner;
  final ReactReflector _reflector;

  Future<ReactRuntimeResult> run({
    required List<Map<String, String>> messages,
    required int maxIterations,
    String goal = '',
    String sessionId = '',
    String? runId,
    String? traceId,
  }) async {
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
    final traces = <AssistantTraceEvent>[
      AssistantTraceEvent(
        type: AssistantTraceEventType.lifecycleStart,
        message: 'agent loop started',
        timestamp: DateTime.now(),
        runId: runId,
        traceId: traceId,
      ),
    ];

    var finalText = '';
    while (!state.shouldStopByIteration && !state.shouldStopByBudget) {
      state.iteration += 1;
      final llmRequestMessages = messages
          .map(
            (m) => <String, String>{
              'role': m['role'] ?? '',
              'content': m['content'] ?? '',
            },
          )
          .toList(growable: false);
      final availableToolNames = _toolRegistry
          .listTools()
          .map((tool) => tool.name)
          .toList(growable: false);
      traces.add(
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
            'messages': llmRequestMessages,
          },
        ),
      );
      final output = await _llmProvider.reason(
        messages: llmRequestMessages,
        availableTools: availableToolNames,
        sessionId: sessionId,
        runId: runId ?? '',
        traceId: traceId ?? '',
      );
      state.plan
        ..clear()
        ..addAll(
          _planner.buildPlan(
            userGoal: state.goal,
            suggestedToolCalls: output.toolCalls,
          ),
        );
      traces.add(
        AssistantTraceEvent(
          type: AssistantTraceEventType.assistantDelta,
          message: output.text,
          timestamp: DateTime.now(),
          runId: runId,
          traceId: traceId,
          data: <String, dynamic>{
            'iteration': state.iteration,
            'degraded': output.degraded,
            'toolCalls': output.toolCalls
                .map(
                  (call) => <String, dynamic>{
                    'name': call.name,
                    'arguments': call.arguments,
                  },
                )
                .toList(growable: false),
          },
        ),
      );
      if (!output.hasToolCalls) {
        finalText = output.text;
        state.stopReason = 'model_answered_without_tools';
        break;
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
        traces.add(
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
            },
          ),
        );
        final toolArguments = <String, dynamic>{
          ...step.arguments,
          '__sessionId': sessionId,
          '__runId': runId ?? '',
          '__traceId': traceId ?? '',
        };
        final result = await _toolRegistry.execute(
          step.toolName,
          toolArguments,
        );
        final isOk = result.success;
        final shouldSuppressToolErrorForUser =
            !isOk &&
            _shouldSuppressToolErrorForUser(step.toolName, result.message);
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
        traces.add(
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
        messages.add(<String, String>{
          'role': 'tool',
          'content': result.message,
        });
        if (!shouldSuppressToolErrorForUser) {
          finalText = result.message;
        } else {
          messages.add(const <String, String>{
            'role': 'system',
            'content':
                '本轮外部检索能力暂不可用。请不要继续调用检索工具，改为基于当前上下文与已有知识直接回答用户问题，并明确说明无法联网检索最新数据。',
          });
        }

        final replan = _reflector.shouldReplan(
          state: state,
          lastStepSuccess: isOk,
          lastMessage: result.message,
        );
        if (replan) {
          state.openQuestions.add('step ${step.id} result needs re-check');
          traces.add(
            AssistantTraceEvent(
              type: AssistantTraceEventType.lifecycleStart,
              message: 'replanning after ${step.id}',
              timestamp: DateTime.now(),
              runId: runId,
              traceId: traceId,
            ),
          );
          break;
        }
      }
    }

    if (finalText.isEmpty) {
      finalText = '本次任务已完成，但没有生成可展示结果。';
    }

    traces.add(
      AssistantTraceEvent(
        type: AssistantTraceEventType.lifecycleEnd,
        message: 'agent loop finished (${state.stopReason ?? 'normal_end'})',
        timestamp: DateTime.now(),
        runId: runId,
        traceId: traceId,
      ),
    );
    return ReactRuntimeResult(finalText: finalText, traces: traces);
  }

  bool _shouldSuppressToolErrorForUser(String toolName, String message) {
    if (toolName != 'web_search' && toolName != 'unified_retrieval') {
      return false;
    }
    final lowered = message.toLowerCase();
    return lowered.contains('missing') ||
        lowered.contains('api key') ||
        lowered.contains('未发现可用搜索 provider') ||
        lowered.contains('检索未找到足够信息') ||
        lowered.contains('检索完成但信息不足') ||
        lowered.contains('network') ||
        lowered.contains('timeout') ||
        lowered.contains('proxy');
  }
}
