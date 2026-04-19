import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/contracts/dialogue_round_script.dart';
import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_round_trace_codec.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/assistant/reasoning/runtime/react_runtime.dart';

void main() {
  test('AssistantRoundTraceCodec 产出 typed round trace 并可序列化', () {
    final codec = AssistantRoundTraceCodec();
    final request = AssistantRunRequest(
      sessionId: 'session-1',
      messages: const <AssistantRunMessage>[
        AssistantRunMessage(role: 'user', content: '帮我查天气'),
      ],
    );
    final result = ReactRuntimeResult(
      finalText: 'final answer',
      traces: <AssistantTraceEvent>[
        AssistantTraceEvent(
          type: AssistantTraceEventType.toolStart,
          message: 'search started',
          timestamp: DateTime.parse('2026-04-08T09:00:00.000Z'),
          toolCallId: 'call-1',
          data: const <String, dynamic>{
            'toolName': 'search',
            'query': '深圳天气',
            'freshnessHoursMax': 6,
          },
        ),
        AssistantTraceEvent(
          type: AssistantTraceEventType.toolResult,
          message: 'search result',
          timestamp: DateTime.parse('2026-04-08T09:00:01.000Z'),
          toolCallId: 'call-1',
        ),
      ],
    );
    const dialogueRoundScript = DialogueRoundScript(
      domainId: 'weather',
      currentStateId: 'search',
      detectedEvent: 'query_weather',
      suggestedNextStateId: 'answer',
      nextStateCandidates: <String>['answer'],
      requiredFieldsForNextState: <String>['city'],
      totalSubTotalRequired: true,
    );

    final trace = codec.build(
      request: request,
      result: result,
      dialogueRoundScript: dialogueRoundScript,
    );
    final json = trace.toJson();

    expect(trace.domainId, 'weather');
    expect(trace.toolCalls.single.toolName, 'search');
    expect(trace.toolCalls.single.arguments['query'], '深圳天气');
    expect(trace.toolResultCount, 1);
    expect(json['toolCalls'], isA<List<dynamic>>());
    expect(
      AssistantRoundTrace.fromJson(json).toolCalls.single.toolCallId,
      'call-1',
    );
  });
}
