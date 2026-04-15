import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/application/assistant_process_timeline_projector.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/contracts/synthesis_readiness_result.dart';
import 'package:quwoquan_app/assistant/infrastructure/llm/llm_provider.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/evidence_digest_phase.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/phase_types.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/understand_phase.dart';
import 'package:quwoquan_app/assistant/orchestration/state/agent_execution_state.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_process_timeline.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/assistant/reasoning/runtime/react_runtime.dart';
import 'package:quwoquan_app/assistant/tool/runtime/tool_registry.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('structured phase streaming contract', () {
    test(
      'understand phase streams stable user-facing field without leaking answer rail',
      () async {
        const expectedSummary = '我先确认你今晚最想知道的是能不能顺利出门。\n再把实时天气和降雨风险核对清楚。';
        final runtime = ReactRuntime(
          llmProvider: _StructuredStreamingLlm(
            rawOutput: jsonEncode(<String, dynamic>{
              'contractId': 'assistant_turn',
              'messageKind': 'progress',
              'phaseId': 'understanding',
              'actionCode': 'frame_problem',
              'reasonCode': 'align_goal',
              'reasonShort': '我先把今晚出门最关键的判断条件确认清楚。',
              'decision': <String, dynamic>{
                'nextAction': 'tool_call',
                'confidence': 0.92,
                'reasoning': '需要先补实时天气依据',
              },
              'userMarkdown': '我先核对实时天气和降雨风险，再给你明确判断。',
              'result': <String, dynamic>{
                'text': '',
                'summary': '进入检索准备',
                'interpretation': '需要先补实时依据',
                'actionHints': const <String>[],
              },
              'selfCheck': <String, dynamic>{
                'goalSatisfied': true,
                'constraintSatisfied': true,
                'safetyBoundarySatisfied': true,
                'failedItems': const <String>[],
              },
              'diagnostics': <String, dynamic>{
                'emergedTags': const <String>[],
                'failedChecks': const <String>[],
                'parseStatus': '',
                'notes': const <String>[],
              },
              'intentGraph': <String, dynamic>{
                'userGoal': '判断今晚深圳是否适合出门',
                'problemShape': 'single_skill',
                'primarySkill': 'fallback_general_search',
                'problemClass': 'realtime_info',
                'answerShape': 'direct_answer',
                'inferredMotive': '想快速判断今晚安排是否需要调整',
                'queryNormalization': <String, dynamic>{
                  'normalizedQuery': '深圳 今晚 天气 出门',
                },
                'queryTasks': <Map<String, dynamic>>[
                  <String, dynamic>{
                    'id': 'weather_live',
                    'query': '深圳 今晚 小时天气',
                    'goal': '确认今晚实时天气与降雨变化',
                    'successCriteria': '拿到实时天气与小时降雨信息',
                  },
                ],
                'globalConstraints': <String, dynamic>{'mode': 'qa'},
              },
              'understandingSnapshot': <String, dynamic>{
                'userFacingSummary': expectedSummary,
                'intentSummary': '用户要判断今晚深圳是否适合出门，重点是实时天气和降雨变化。',
                'concernPoints': const <String>['实时天气', '降雨风险'],
                'emotionSignal': 'neutral',
              },
            }),
            fieldPath: 'understandingSnapshot.userFacingSummary',
            fieldDeltas: const <String>[
              '我先确认你今晚最想知道的是能不能顺利出门。',
              '\n再把实时天气和降雨风险核对清楚。',
            ],
          ),
          toolRegistry: AssistantToolRegistry(),
        );
        final traces = <AssistantTraceEvent>[];
        final phase = UnderstandPhase(runtime: runtime);

        final output = await phase.run(
          PhaseInput(
            request: const AssistantRunRequest(
              sessionId: 'understand_streaming_contract',
              messages: <AssistantRunMessage>[
                AssistantRunMessage(role: 'user', content: '深圳今晚适合出门吗'),
              ],
            ),
            state: const AgentExecutionState(),
            runId: 'run_understand_streaming_contract',
            traceId: 'trace_understand_streaming_contract',
            onTraceEvent: (dynamic event) =>
                traces.add(event as AssistantTraceEvent),
          ),
        );

        expect(
          output.state?.understandingSnapshot.userFacingSummary,
          equals(expectedSummary),
        );
        expect(
          traces.where(
            (trace) => trace.type == AssistantTraceEventType.streamDelta,
          ),
          isEmpty,
          reason: '理解阶段的结构化流式不应误入答案主轨',
        );
        expect(
          _syntheticProcessEventTypes(traces, ProcessStepId.understanding),
          containsAllInOrder(<String>[
            'process_replace',
            'process_append',
            'process_commit',
          ]),
        );
        final timeline = buildVisibleProcessTimeline(
          AssistantProcessTimelineProjector.replay(traces: traces),
        );
        final understandingFrame = timeline.firstWhere(
          (frame) => frame.stepId == ProcessStepId.understanding,
        );
        expect(understandingFrame.headline, equals(expectedSummary));
      },
    );

    test(
      'understand phase falls back to streamed summary when final payload omits it',
      () async {
        const expectedSummary = '你这次是想确认深圳现在适不适合出门。\n我会先把实时天气和降雨变化核对清楚。';
        final runtime = ReactRuntime(
          llmProvider: _StructuredStreamingLlm(
            rawOutput: jsonEncode(<String, dynamic>{
              'contractId': 'assistant_turn',
              'messageKind': 'progress',
              'phaseId': 'understanding',
              'actionCode': 'frame_problem',
              'reasonCode': 'align_goal',
              'reasonShort': '我先把出门判断最关键的条件确认清楚。',
              'decision': <String, dynamic>{
                'nextAction': 'tool_call',
                'confidence': 0.88,
              },
              'intentGraph': <String, dynamic>{
                'userGoal': '确认深圳现在是否适合出门',
                'problemShape': 'single_skill',
                'primarySkill': 'fallback_general_search',
                'problemClass': 'realtime_info',
                'answerShape': 'direct_answer',
                'queryNormalization': <String, dynamic>{
                  'normalizedQuery': '深圳 实时天气 出门',
                },
              },
              'understandingSnapshot': <String, dynamic>{
                'userFacingSummary': '',
                'intentSummary': '用户想确认深圳现在适不适合出门。',
                'concernPoints': const <String>['实时天气', '降雨变化'],
                'emotionSignal': 'neutral',
              },
            }),
            fieldPath: 'understandingSnapshot.userFacingSummary',
            fieldDeltas: const <String>[
              '你这次是想确认深圳现在适不适合出门。',
              '\n我会先把实时天气和降雨变化核对清楚。',
            ],
          ),
          toolRegistry: AssistantToolRegistry(),
        );
        final phase = UnderstandPhase(runtime: runtime);
        final traces = <AssistantTraceEvent>[];

        final output = await phase.run(
          PhaseInput(
            request: const AssistantRunRequest(
              sessionId: 'understand_streamed_summary_recovery',
              messages: <AssistantRunMessage>[
                AssistantRunMessage(role: 'user', content: '深圳现在适合出门吗'),
              ],
            ),
            state: const AgentExecutionState(),
            runId: 'run_understand_streamed_summary_recovery',
            traceId: 'trace_understand_streamed_summary_recovery',
            onTraceEvent: (dynamic event) =>
                traces.add(event as AssistantTraceEvent),
          ),
        );

        expect(
          output.state?.understandingSnapshot.userFacingSummary,
          equals(expectedSummary),
        );
        expect(
          traces.any(
            (trace) =>
                trace.type == AssistantTraceEventType.thinkingProgress &&
                trace.data?['fieldPath'] ==
                    'understandingSnapshot.userFacingSummary',
          ),
          isTrue,
        );
      },
    );

    test(
      'evidence digest phase 在普通 ready 链路只缓存 fallback processingSummary，不单独发流式过程事件',
      () async {
        const expectedSummary =
            '降雨风险、体感温度方面，已有可信证据指向以下判断：今晚前半夜降雨概率低，体感温度适中。';
        final traces = <AssistantTraceEvent>[];
        final phase = EvidenceDigestPhase();
        final phaseOneResult = ReactRuntimeResult(
          finalText: '',
          traces: <AssistantTraceEvent>[
            AssistantTraceEvent(
              type: AssistantTraceEventType.toolResult,
              message: 'weather search result',
              timestamp: DateTime.now(),
              data: <String, dynamic>{
                'totalReferences': 4,
                'references': <Map<String, dynamic>>[
                  <String, dynamic>{
                    'title': '深圳天气实况',
                    'url': 'https://example.com/weather',
                    'source': 'example.com',
                    'snippet': '今晚前半夜降雨概率低，体感温度适中。',
                  },
                ],
              },
            ),
          ],
        );

        final output = await phase.run(
          PhaseInput(
            request: const AssistantRunRequest(
              sessionId: 'evidence_digest_streaming_contract',
              messages: <AssistantRunMessage>[
                AssistantRunMessage(role: 'user', content: '深圳今晚适合出门吗'),
              ],
            ),
            state: AgentExecutionState(
              understandingSnapshot: const RunArtifactsUnderstandingSnapshot(
                userFacingSummary: '我先确认你今晚最想知道的是能不能顺利出门。',
                concernPoints: <String>['降雨风险', '体感温度'],
              ),
              executionBridgeSnapshot: <String, dynamic>{
                'phaseOneResult': phaseOneResult,
                'synthesisReadiness': const SynthesisReadinessResult(
                  ready: true,
                ),
              },
            ),
            runId: 'run_evidence_digest_streaming_contract',
            traceId: 'trace_evidence_digest_streaming_contract',
            onTraceEvent: (dynamic event) =>
                traces.add(event as AssistantTraceEvent),
          ),
        );

        expect(
          output.state?.retrievalProcessing.processingSummary,
          equals(expectedSummary),
        );
        expect(
          traces.where(
            (trace) => trace.type == AssistantTraceEventType.streamDelta,
          ),
          isEmpty,
          reason: '普通链路的阶段2流式应在 synthesis 第二轮输出，evidence digest 不应单独再起一轮',
        );
        expect(
          _syntheticProcessEventTypes(
            traces,
            ProcessStepId.retrievalProcessing,
          ),
          isEmpty,
        );
      },
    );
  });
}

List<String> _syntheticProcessEventTypes(
  List<AssistantTraceEvent> traces,
  ProcessStepId stepId,
) {
  return traces
      .where(
        (trace) =>
            trace.data?['syntheticUserEvent'] == true &&
            trace.data?['processStepId'] == stepId.wireName,
      )
      .map((trace) => (trace.data?['userEventType'] as String?) ?? '')
      .where((item) => item.isNotEmpty)
      .toList(growable: false);
}

class _StructuredStreamingLlm extends SwitchableAssistantLlmProvider {
  _StructuredStreamingLlm({
    required this.rawOutput,
    required this.fieldPath,
    required this.fieldDeltas,
  }) : super(fallbackProvider: const ModelOnlyFailureLlmProvider());

  final String rawOutput;
  final String fieldPath;
  final List<String> fieldDeltas;

  @override
  Future<String> reasonStream({
    required List<Map<String, dynamic>> messages,
    required List<String> availableTools,
    required void Function(String delta) onDelta,
    List<String> streamJsonFieldPaths = const <String>[],
    void Function(String fieldPath, String delta)? onStructuredDelta,
    void Function(String failureCode, Map<String, dynamic> diagnostics)?
    onFailure,
    Map<String, dynamic> templateContext = const <String, dynamic>{},
    Map<String, dynamic> templateVariables = const <String, dynamic>{},
    String templateId = 'synthesizer.final_answer',
    String templateVersion = '',
    String sessionId = '',
    String runId = '',
    String traceId = '',
  }) async {
    for (final delta in fieldDeltas) {
      onDelta(delta);
    }
    if (streamJsonFieldPaths.contains(fieldPath)) {
      for (final delta in fieldDeltas) {
        onStructuredDelta?.call(fieldPath, delta);
      }
    }
    return rawOutput;
  }

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
    return AssistantModelOutput(text: rawOutput);
  }
}
