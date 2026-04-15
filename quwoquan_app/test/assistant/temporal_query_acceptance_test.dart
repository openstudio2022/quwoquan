import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/infrastructure/assistant_model_runtime.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/phase_types.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/retrieval_design_phase.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/understand_phase.dart';
import 'package:quwoquan_app/assistant/orchestration/state/agent_execution_state.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_display_state_projection.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_process_timeline.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_journey.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/reasoning/runtime/react_runtime.dart';
import 'package:quwoquan_app/assistant/tool/runtime/tool_registry.dart';
import 'package:quwoquan_app/assistant/tool/schema/tool_schema.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('相对时间问题会在规划、展示与答案区形成同一套具体日期语义', () async {
    const cases = <_TemporalAcceptanceCase>[
      _TemporalAcceptanceCase(
        query: '昨天A股为什么大涨',
        referenceNowIso: '2026-04-08T10:30:00.000',
        timezone: 'Asia/Shanghai',
        expectedQuery: '2026-04-07 A股 大涨 原因',
      ),
      _TemporalAcceptanceCase(
        query: '今天A股为什么大涨',
        referenceNowIso: '2026-04-08T10:30:00.000',
        timezone: 'Asia/Shanghai',
        expectedQuery: '2026-04-08 A股 大涨 原因',
      ),
      _TemporalAcceptanceCase(
        query: '明天天气怎么样',
        referenceNowIso: '2026-04-08T10:30:00.000',
        timezone: 'Asia/Shanghai',
        expectedQuery: '2026-04-09 天气 预报',
      ),
      _TemporalAcceptanceCase(
        query: '后天天气怎么样',
        referenceNowIso: '2026-04-08T10:30:00.000',
        timezone: 'Asia/Shanghai',
        expectedQuery: '2026-04-10 天气 预报',
      ),
      _TemporalAcceptanceCase(
        query: '周三A股为什么大涨',
        referenceNowIso: '2026-04-10T09:30:00.000',
        timezone: 'Asia/Shanghai',
        expectedQuery: '2026-04-08 A股 大涨 原因',
      ),
      _TemporalAcceptanceCase(
        query: '上周三A股为什么大涨',
        referenceNowIso: '2026-04-10T09:30:00.000',
        timezone: 'Asia/Shanghai',
        expectedQuery: '2026-04-01 A股 大涨 原因',
      ),
      _TemporalAcceptanceCase(
        query: '下周三深圳天气怎么样',
        referenceNowIso: '2026-04-09T10:30:00.000',
        timezone: 'Asia/Shanghai',
        expectedQuery: '2026-04-15 深圳 天气 预报',
      ),
      _TemporalAcceptanceCase(
        query: '最近股市走向怎么样',
        referenceNowIso: '2026-04-09T10:30:00.000',
        timezone: 'Asia/Shanghai',
        expectedQuery: '2026-03-09 至 2026-04-09 A股 走势',
      ),
      _TemporalAcceptanceCase(
        query: '结合最近股市走向及国际经济形势，预测下未来股市走向',
        referenceNowIso: '2026-04-09T10:30:00.000',
        timezone: 'Asia/Shanghai',
        expectedQuery: '2026-03-09 至 2026-04-09 结合最近股市 A股 走势 国际经济 股市走势预测',
      ),
    ];

    for (final testCase in cases) {
      final provider = _DeterministicPlannerProvider(
        expectedQuery: testCase.expectedQuery,
      );
      final toolRegistry = AssistantToolRegistry()
        ..register(_NoopWebSearchTool());
      final runtime = ReactRuntime(
        llmProvider: provider,
        toolRegistry: toolRegistry,
      );
      final request = AssistantRunRequest(
        messages: <AssistantRunMessage>[
          AssistantRunMessage(role: 'user', content: testCase.query),
        ],
        contextScopeHint: <String, dynamic>{
          'requiresExternalEvidence': true,
          'referenceNowIso': testCase.referenceNowIso,
          'timezone': testCase.timezone,
        },
      );

      final understandOutput = await UnderstandPhase(runtime: runtime).run(
        PhaseInput(
          request: request,
          state: AgentExecutionState(),
          runId: 'run_${testCase.expectedQuery.hashCode}',
          traceId: 'trace_${testCase.expectedQuery.hashCode}',
        ),
      );
      final understandState = understandOutput.state!;

      expect(
        understandState.intentGraph?.queryNormalization.referenceNowIso,
        testCase.referenceNowIso,
      );
      expect(
        understandState.intentGraph?.queryNormalization.timezone,
        testCase.timezone,
      );

      final retrievalOutput = await RetrievalDesignPhase(runtime: runtime).run(
        PhaseInput(
          request: request,
          state: understandState,
          runId: 'run_${testCase.expectedQuery.hashCode}',
          traceId: 'trace_${testCase.expectedQuery.hashCode}',
        ),
      );
      final retrievalState = retrievalOutput.state!;

      expect(retrievalState.queryTasks, isNotEmpty, reason: testCase.query);
      for (final task in retrievalState.queryTasks) {
        expect(task.timeScope, isEmpty, reason: testCase.query);
        expect(task.timePoint, isEmpty, reason: testCase.query);
        expect(
          task.query,
          equals(testCase.expectedQuery),
          reason: testCase.query,
        );
      }

      final displayState = buildAssistantDisplayState(
        processTimeline: <ProcessTimelineFrame>[
          buildProcessTimelineFrame(
            stepId: ProcessStepId.understanding,
            status: JourneyStageStatus.completed,
            understandingSnapshot: retrievalState.understandingSnapshot,
          ),
          buildProcessTimelineFrame(
            stepId: ProcessStepId.retrievalDesign,
            status: JourneyStageStatus.completed,
            detail: '执行检索：${retrievalState.queryTasks.first.query}',
          ),
          const ProcessTimelineFrame(
            frameId: 'r',
            stepId: ProcessStepId.retrievalProcessing,
            status: JourneyStageStatus.completed,
          ),
          const ProcessTimelineFrame(
            frameId: 'a',
            stepId: ProcessStepId.answerOrganization,
            status: JourneyStageStatus.completed,
          ),
        ],
        understandingSnapshot: retrievalState.understandingSnapshot,
        retrievalProcessing: const RetrievalProcessingSnapshot(
          processingSummary: '已经筛出首轮可用线索。',
        ),
        answerProcessing: const RunArtifactsAnswerProcessing(
          readinessSummary: '我开始把确认过的信息整理成答案。',
        ),
        answerMarkdown: '测试答案',
        finalAnswerReady: true,
      );

      final narrative = displayState.process.blocks
          .where((block) => block.blockId == 'understanding_narrative')
          .map((block) => '${block.title}\n${block.body}')
          .join('\n');
      expect(
        narrative,
        contains(testCase.expectedQuery),
        reason: testCase.query,
      );
      expect(displayState.answer.blocks, isNotEmpty, reason: testCase.query);
      expect(
        renderAnswerBlocksToMarkdown(displayState.answer.blocks),
        contains('测试答案'),
      );
    }
  });

  test('模型回传错误 retrieval design 时，展示仍以 canonical queryTasks 为准', () async {
    final provider = _ConflictingTemporalQueryGroupProvider();
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

    final understandOutput = await UnderstandPhase(runtime: runtime).run(
      PhaseInput(
        request: request,
        state: AgentExecutionState(),
        runId: 'run_conflicting_query_groups',
        traceId: 'trace_conflicting_query_groups',
      ),
    );
    final retrievalOutput = await RetrievalDesignPhase(runtime: runtime).run(
      PhaseInput(
        request: request,
        state: understandOutput.state!,
        runId: 'run_conflicting_query_groups',
        traceId: 'trace_conflicting_query_groups',
      ),
    );
    final canonicalQuery = retrievalOutput.state!.queryTasks.first.query;
    final displayState = buildAssistantDisplayState(
      processTimeline: <ProcessTimelineFrame>[
        buildProcessTimelineFrame(
          stepId: ProcessStepId.understanding,
          status: JourneyStageStatus.completed,
          understandingSnapshot: retrievalOutput.state!.understandingSnapshot,
        ),
        buildProcessTimelineFrame(
          stepId: ProcessStepId.retrievalDesign,
          status: JourneyStageStatus.completed,
          detail: '执行检索：$canonicalQuery',
        ),
        const ProcessTimelineFrame(
          frameId: 'r',
          stepId: ProcessStepId.retrievalProcessing,
          status: JourneyStageStatus.completed,
        ),
      ],
      understandingSnapshot: retrievalOutput.state!.understandingSnapshot,
      retrievalProcessing: const RetrievalProcessingSnapshot(
        processingSummary: '已经筛出首轮可用线索。',
      ),
    );

    expect(canonicalQuery, contains('2026-04-08'));
    expect(canonicalQuery, isNot(contains('2026-04-09 A股 大涨 原因')));
    final narrative = displayState.process.blocks
        .where((block) => block.blockId == 'understanding_narrative')
        .map((block) => '${block.title}\n${block.body}')
        .join('\n');
    expect(narrative, contains('2026-04-08 A股 大涨 原因'));
    expect(narrative, isNot(contains('2026-04-09 A股 大涨 原因')));
  });
}

class _TemporalAcceptanceCase {
  const _TemporalAcceptanceCase({
    required this.query,
    required this.referenceNowIso,
    required this.timezone,
    required this.expectedQuery,
  });

  final String query;
  final String referenceNowIso;
  final String timezone;
  final String expectedQuery;
}

class _DeterministicPlannerProvider implements AssistantLlmProvider {
  _DeterministicPlannerProvider({required this.expectedQuery});

  final String expectedQuery;

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
    return AssistantModelOutput(
      text: jsonEncode(<String, dynamic>{
        'contractId': 'assistant_turn',
        'messageKind': 'progress',
        'phaseId': 'understanding',
        'actionCode': 'frame_problem',
        'reasonCode': 'align_goal',
        'reasonShort': '先确定时间范围，再组织检索。',
        'decision': const <String, dynamic>{'nextAction': 'tool_call'},
        'understandingSnapshot': const <String, dynamic>{
          'userFacingSummary': '我先把问题里的时间指向具体日历点。',
          'intentSummary': '用户需要实时/指定日期的信息结论。',
          'concernPoints': <String>['时间落点', '外部证据'],
        },
        'intentGraph': <String, dynamic>{
          'userGoal': '获取相对时间对应的外部结论',
          'problemShape': 'single_skill',
          'primarySkill': 'general_search',
          'problemClass': 'realtime_info',
          'inferredMotive': '需要基于外部证据回答',
          'secondarySkills': <String>[],
          'queryNormalization': <String, dynamic>{
            'normalizedQuery': expectedQuery,
          },
          'queryTasks': <Map<String, dynamic>>[
            <String, dynamic>{
              'id': 'time_anchor_lookup',
              'query': expectedQuery,
              'dimension': 'latest_signal',
              'why': '直接输出最终可执行检索词，运行时不再二次改写时间。',
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

class _ConflictingTemporalQueryGroupProvider implements AssistantLlmProvider {
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
    return AssistantModelOutput(
      text: jsonEncode(<String, dynamic>{
        'contractId': 'assistant_turn',
        'messageKind': 'progress',
        'phaseId': 'understanding',
        'actionCode': 'frame_problem',
        'reasonCode': 'align_goal',
        'decision': const <String, dynamic>{'nextAction': 'tool_call'},
        'understandingSnapshot': const <String, dynamic>{
          'userFacingSummary': '我先把周三对应到具体交易日，再组织检索。',
        },
        'intentGraph': <String, dynamic>{
          'userGoal': '获取周三A股上涨原因',
          'problemShape': 'single_skill',
          'primarySkill': 'general_search',
          'problemClass': 'realtime_info',
          'secondarySkills': <String>[],
          'queryNormalization': <String, dynamic>{
            'normalizedQuery': '2026-04-08 A股 大涨 原因',
          },
          'queryTasks': <Map<String, dynamic>>[
            <String, dynamic>{
              'id': 'market_jump',
              'query': '2026-04-08 A股 大涨 原因',
              'dimension': 'latest_signal',
              'why': '先锁定具体交易日，再看对应盘面和消息面。',
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
