import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/application/assistant_process_timeline_projector.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/contracts/synthesis_readiness_result.dart';
import 'package:quwoquan_app/assistant/infrastructure/llm/llm_provider.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/evidence_digest_phase.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/phase.dart';
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
    test('understand phase streams stable user-facing field without leaking answer rail', () async {
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
              'queryDesignSummary': '优先核对实时天气、小时降雨和预警变化。',
              'queryGroups': <Map<String, dynamic>>[
                <String, dynamic>{
                  'dimension': '实时天气',
                  'queries': const <String>['深圳 今晚 小时天气'],
                  'why': '先补最影响出门判断的条件',
                },
              ],
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
          onTraceEvent: (dynamic event) => traces.add(event as AssistantTraceEvent),
        ),
      );

      expect(
        output.state?.understandingSnapshot.userFacingSummary,
        equals(expectedSummary),
      );
      expect(
        traces.where((trace) => trace.type == AssistantTraceEventType.streamDelta),
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
    });

    test('evidence digest phase streams processingSummary field without answer leakage', () async {
      const expectedSummary = '这批结果里真正能支撑回答的是今晚降雨风险和体感温度。\n目前已经足够判断是否适合出门。';
      final runtime = ReactRuntime(
        llmProvider: _StructuredStreamingLlm(
          rawOutput: jsonEncode(<String, dynamic>{
            'retrievalProcessing': <String, dynamic>{
              'processedDocumentCount': 4,
              'acceptedDocumentCount': 2,
              'processingSummary': expectedSummary,
              'selectedKeyPoints': const <String>[
                '今晚前半夜降雨概率低',
                '当前体感温度适中',
              ],
              'expansionReason': '',
              'acceptedReferences': <Map<String, dynamic>>[
                <String, dynamic>{
                  'title': '深圳天气实况',
                  'url': 'https://example.com/weather',
                  'source': 'example.com',
                  'snippet': '今晚前半夜降雨概率低，体感温度适中。',
                },
              ],
            },
          }),
          fieldPath: 'retrievalProcessing.processingSummary',
          fieldDeltas: const <String>[
            '这批结果里真正能支撑回答的是今晚降雨风险和体感温度。',
            '\n目前已经足够判断是否适合出门。',
          ],
        ),
        toolRegistry: AssistantToolRegistry(),
      );
      final traces = <AssistantTraceEvent>[];
      final phase = EvidenceDigestPhase(runtime: runtime);
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
              'synthesisReadiness': const SynthesisReadinessResult(ready: true),
            },
          ),
          runId: 'run_evidence_digest_streaming_contract',
          traceId: 'trace_evidence_digest_streaming_contract',
          onTraceEvent: (dynamic event) => traces.add(event as AssistantTraceEvent),
        ),
      );

      expect(
        output.state?.retrievalProcessing.processingSummary,
        equals(expectedSummary),
      );
      expect(
        traces.where((trace) => trace.type == AssistantTraceEventType.streamDelta),
        isEmpty,
        reason: '结果处理阶段的结构化流式不应误入答案主轨',
      );
      expect(
        _syntheticProcessEventTypes(traces, ProcessStepId.retrievalProcessing),
        containsAllInOrder(<String>[
          'process_replace',
          'process_append',
          'process_commit',
        ]),
      );
      final timeline = buildVisibleProcessTimeline(
        AssistantProcessTimelineProjector.replay(traces: traces),
      );
      final retrievalFrame = timeline.firstWhere(
        (frame) => frame.stepId == ProcessStepId.retrievalProcessing,
      );
      expect(retrievalFrame.headline, equals(expectedSummary));
    });
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
    this.visibleDeltas = const <String>['这段可见文本不应进入答案主轨'],
  }) : super(fallbackProvider: const ModelOnlyFailureLlmProvider());

  final String rawOutput;
  final String fieldPath;
  final List<String> fieldDeltas;
  final List<String> visibleDeltas;

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
    for (final delta in visibleDeltas) {
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
