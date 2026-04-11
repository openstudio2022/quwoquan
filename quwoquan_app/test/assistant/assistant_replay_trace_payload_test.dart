import 'package:quwoquan_app/assistant/protocol/assistant_replay_trace_payload.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';
import 'package:test/test.dart';

void main() {
  test('fromTraces picks last tool diagnostics and last structured search payload', () {
    final ts = DateTime.now();
    final traces = <AssistantTraceEvent>[
      AssistantTraceEvent(
        type: AssistantTraceEventType.toolResult,
        message: 'm1',
        timestamp: ts,
        data: <String, dynamic>{
          'diagnostics': <String, dynamic>{'a': 1},
          'queryPlan': <String, dynamic>{'old': true},
        },
      ),
      AssistantTraceEvent(
        type: AssistantTraceEventType.toolError,
        message: 'err',
        timestamp: ts,
        data: <String, dynamic>{
          'diagnostics': <String, dynamic>{'b': 2},
        },
      ),
      AssistantTraceEvent(
        type: AssistantTraceEventType.toolResult,
        message: 'm2',
        timestamp: ts,
        data: <String, dynamic>{
          'queryPlan': <String, dynamic>{'q': 1},
          'policyDecision': <String, dynamic>{'p': 2},
          'roundTraces': <Map<String, dynamic>>[
            <String, dynamic>{'k': 'v'},
          ],
        },
      ),
    ];
    final payload = AssistantReplayTracePayload.fromTraces(traces);
    expect(payload.webSearchDiagnostics, <String, dynamic>{'b': 2});
    expect(payload.queryPlan, <String, dynamic>{'q': 1});
    expect(payload.policyDecision, <String, dynamic>{'p': 2});
    expect(payload.roundTraces.length, 1);
    expect(payload.roundTraces.first['k'], 'v');
    expect(
      payload.toPayloadMap()['webSearchDiagnostics'],
      payload.webSearchDiagnostics,
    );
  });

  test('fromTraces returns empty maps when no tool payloads', () {
    final ts = DateTime.now();
    final traces = <AssistantTraceEvent>[
      AssistantTraceEvent(
        type: AssistantTraceEventType.answerDelta,
        message: 'x',
        timestamp: ts,
      ),
    ];
    final payload = AssistantReplayTracePayload.fromTraces(traces);
    expect(payload.queryPlan, isEmpty);
    expect(payload.policyDecision, isEmpty);
    expect(payload.roundTraces, isEmpty);
    expect(payload.webSearchDiagnostics, isEmpty);
  });
}
