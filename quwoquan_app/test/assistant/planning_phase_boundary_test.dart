import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/infrastructure/assistant_model_runtime.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/phase_types.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/retrieval_design_phase.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/understand_phase.dart';
import 'package:quwoquan_app/assistant/orchestration/state/agent_execution_state.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/reasoning/runtime/react_runtime.dart';
import 'package:quwoquan_app/assistant/tool/runtime/tool_registry.dart';
import 'package:quwoquan_app/assistant/tool/schema/tool_schema.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test(
    'UnderstandPhase 负责生成 queryTasks，RetrievalDesignPhase 只做归一化不再二次规划',
    () async {
      final provider = _CapturePlannerProvider();
      final toolRegistry = AssistantToolRegistry()
        ..register(_NoopWebSearchTool());
      final runtime = ReactRuntime(
        llmProvider: provider,
        toolRegistry: toolRegistry,
      );
      final request = const AssistantRunRequest(
        messages: <AssistantRunMessage>[
          AssistantRunMessage(role: 'user', content: '今天深圳天气怎么样'),
        ],
        contextScopeHint: <String, dynamic>{
          'requiresExternalEvidence': true,
          'referenceNowIso': '2026-04-08T10:30:00.000',
          'timezone': 'Asia/Shanghai',
        },
      );

      final understandOutput = await UnderstandPhase(runtime: runtime).run(
        PhaseInput(
          request: request,
          state: AgentExecutionState(),
          runId: 'run_planning_phase',
          traceId: 'trace_planning_phase',
        ),
      );

      expect(provider.plannerCalls, 1);
      expect(
        provider.lastTemplateContext['referenceNowIso'],
        '2026-04-08T10:30:00.000',
      );
      expect(provider.lastTemplateContext['timezone'], 'Asia/Shanghai');
      expect(
        (provider.lastTemplateVariables['currentRuntimeState'] as String?) ??
            '',
        contains('referenceNowIso'),
      );
      expect(
        (provider.lastTemplateVariables['currentRuntimeState'] as String?) ??
            '',
        contains('Asia/Shanghai'),
      );
      final searchIterationState =
          jsonDecode(
                (provider.lastTemplateVariables['searchIterationState']
                        as String?) ??
                    '{}',
              )
              as Map<String, dynamic>;
      expect(searchIterationState['maxIterations'], 5);
      expect(searchIterationState['currentIteration'], 1);
      final understandState = understandOutput.state;
      expect(understandState, isNotNull);
      expect(understandState!.queryTasks, isNotEmpty);
      expect(
        understandState.intentGraph?.queryNormalization.referenceNowIso,
        '2026-04-08T10:30:00.000',
      );
      expect(
        understandState.intentGraph?.queryNormalization.timezone,
        'Asia/Shanghai',
      );
      expect(
        understandState.intentGraph?.queryNormalization.timeScope,
        isEmpty,
      );
      expect(
        understandState.intentGraph?.queryNormalization.timePoint,
        isEmpty,
      );
      for (final task in understandState.queryTasks) {
        expect(task.timeScope, isEmpty);
        expect(task.timePoint, isEmpty);
        expect(task.query, equals('深圳 2026-04-08 实时天气'));
      }
      final plannedTaskIds = understandState.queryTasks
          .map((task) => task.id)
          .toList(growable: false);

      final retrievalOutput = await RetrievalDesignPhase(runtime: runtime).run(
        PhaseInput(
          request: request,
          state: understandState,
          runId: 'run_planning_phase',
          traceId: 'trace_planning_phase',
        ),
      );

      expect(provider.plannerCalls, 1);
      final retrievalState = retrievalOutput.state;
      expect(retrievalState, isNotNull);
      expect(
        retrievalState!.queryTasks
            .map((task) => task.id)
            .toList(growable: false),
        orderedEquals(plannedTaskIds),
      );
      expect(
        retrievalState.queryTasks.every(
          (task) =>
              task.query == '深圳 2026-04-08 实时天气' &&
              task.timePoint.isEmpty &&
              task.timeScope.isEmpty,
        ),
        isTrue,
      );
    },
  );

  test('planner template vars 会注入 calendarContext，供模型校准周几锚点', () async {
    final provider = _CapturePlannerProvider();
    final toolRegistry = AssistantToolRegistry()
      ..register(_NoopWebSearchTool());
    final runtime = ReactRuntime(
      llmProvider: provider,
      toolRegistry: toolRegistry,
    );
    final request = const AssistantRunRequest(
      messages: <AssistantRunMessage>[
        AssistantRunMessage(role: 'user', content: '周三A股为什么大涨'),
      ],
      contextScopeHint: <String, dynamic>{
        'requiresExternalEvidence': true,
        'referenceNowIso': '2026-04-09T10:30:00.000',
        'timezone': 'Asia/Shanghai',
      },
    );

    await UnderstandPhase(runtime: runtime).run(
      PhaseInput(
        request: request,
        state: AgentExecutionState(),
        runId: 'run_weekday_calendar_context',
        traceId: 'trace_weekday_calendar_context',
      ),
    );

    final sharedContext =
        jsonDecode(
              (provider.lastTemplateVariables['sharedContext'] as String?) ??
                  '{}',
            )
            as Map<String, dynamic>;
    final temporalReference =
        (sharedContext['temporalReference'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final calendarContext =
        (temporalReference['calendarContext'] as Map?)
            ?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final today =
        (calendarContext['today'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final dayBeforeYesterday =
        (calendarContext['dayBeforeYesterday'] as Map?)
            ?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final dayAfterTomorrow =
        (calendarContext['dayAfterTomorrow'] as Map?)
            ?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final thisWeek =
        (calendarContext['thisWeek'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final lastWeek =
        (calendarContext['lastWeek'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final nextWeek =
        (calendarContext['nextWeek'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};

    expect(today['date'], '2026-04-09');
    expect(today['weekday'], '周四');
    expect(dayBeforeYesterday['date'], '2026-04-07');
    expect(dayAfterTomorrow['date'], '2026-04-11');
    expect(thisWeek['周三'], '2026-04-08');
    expect(lastWeek['周三'], '2026-04-01');
    expect(nextWeek['周三'], '2026-04-15');

    final currentRuntimeState =
        jsonDecode(
              (provider.lastTemplateVariables['currentRuntimeState']
                      as String?) ??
                  '{}',
            )
            as Map<String, dynamic>;
    final dialogueState =
        (currentRuntimeState['dialogueState'] as Map?)
            ?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final runtimeCalendarContext =
        (dialogueState['calendarContext'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final runtimeThisWeek =
        (runtimeCalendarContext['thisWeek'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    expect(runtimeThisWeek['周三'], '2026-04-08');
  });
}

class _CapturePlannerProvider implements AssistantLlmProvider {
  int plannerCalls = 0;
  Map<String, dynamic> lastTemplateContext = const <String, dynamic>{};
  Map<String, dynamic> lastTemplateVariables = const <String, dynamic>{};

  @override
  Future<AssistantModelOutput> reason({
    required List<Map<String, dynamic>> messages,
    required List<String> availableTools,
    Map<String, dynamic> templateContext = const <String, dynamic>{},
    Map<String, dynamic> templateVariables = const <String, dynamic>{},
    String templateId = 'planner.global_plan',
    String templateVersion = '',
    String sessionId = '',
    String runId = '',
    String traceId = '',
    LlmCallOptions? callOptions,
    void Function(String delta)? onDelta,
  }) async {
    if (templateId == 'planner.global_plan') {
      plannerCalls += 1;
    }
    lastTemplateContext = Map<String, dynamic>.from(templateContext);
    lastTemplateVariables = Map<String, dynamic>.from(templateVariables);
    return AssistantModelOutput(
      text: jsonEncode(<String, dynamic>{
        'contractId': 'assistant_turn',
        'messageKind': 'progress',
        'phaseId': 'understanding',
        'actionCode': 'frame_problem',
        'reasonCode': 'align_goal',
        'reasonShort': '先识别实时天气问题，再组织检索。',
        'decision': const <String, dynamic>{'nextAction': 'tool_call'},
        'understandingSnapshot': const <String, dynamic>{
          'userFacingSummary': '我先核对深圳今天的实时天气。',
          'intentSummary': '用户需要实时天气结论。',
          'concernPoints': <String>['天气现状', '体感'],
        },
        'intentGraph': const <String, dynamic>{
          'userGoal': '获取深圳今天实时天气',
          'problemShape': 'single_skill',
          'primarySkill': 'weather',
          'problemClass': 'realtime_info',
          'inferredMotive': '想知道深圳今天天气',
          'secondarySkills': <String>[],
          'queryNormalization': <String, dynamic>{
            'normalizedQuery': '深圳 今日 天气 实时',
          },
          'queryTasks': <Map<String, dynamic>>[
            <String, dynamic>{
              'id': 'weather_today',
              'query': '深圳 2026-04-08 实时天气',
              'dimension': 'current_state',
              'why': '直接把今天落成具体日期，避免运行时再猜时间。',
            },
          ],
          'contextSlots': <String, dynamic>{},
          'globalConstraints': <String, dynamic>{'mode': 'qa'},
          'clarificationNeeded': false,
          'requiresExternalEvidence': true,
          'answerShape': 'decision_ready',
          'freshnessNeed': 'latest',
          'freshnessHoursMax': 6,
        },
        'selfCheck': const <String, dynamic>{
          'goalSatisfied': true,
          'constraintSatisfied': true,
          'safetyBoundarySatisfied': true,
          'failedItems': <String>[],
        },
        'diagnostics': const <String, dynamic>{
          'emergedTags': <String>[],
          'failedChecks': <String>[],
          'notes': <String>[],
        },
      }),
    );
  }
}

class _NoopWebSearchTool implements AssistantTool {
  @override
  String get name => 'web_search';

  @override
  String get description => 'noop web search';

  @override
  Future<AssistantToolResult> execute(Map<String, dynamic> arguments) async {
    return const AssistantToolResult(success: true, message: 'noop');
  }
}
