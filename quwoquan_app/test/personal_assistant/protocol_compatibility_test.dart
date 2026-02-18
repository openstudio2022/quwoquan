import 'package:quwoquan_app/personal_assistant/protocol/run_request.dart';
import 'package:quwoquan_app/personal_assistant/protocol/run_response.dart';
import 'package:quwoquan_app/personal_assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/personal_assistant/tools/tool_schema.dart';
import 'package:test/test.dart';

void main() {
  group('Protocol compatibility', () {
    test('run request supports json roundtrip', () {
      const request = AssistantRunRequest(
        messages: <AssistantRunMessage>[
          AssistantRunMessage(role: 'user', content: 'hello'),
          AssistantRunMessage(role: 'assistant', content: 'hi'),
        ],
        sessionId: 's1',
        userId: 'u1',
        deviceProfile: 'mobile',
        maxIterations: 3,
      );

      final decoded = AssistantRunRequest.fromJson(request.toJson());
      expect(decoded.sessionId, equals('s1'));
      expect(decoded.userId, equals('u1'));
      expect(decoded.deviceProfile, equals('mobile'));
      expect(decoded.maxIterations, equals(3));
      expect(decoded.messages.length, equals(2));
    });

    test('run response supports json roundtrip', () {
      final response = AssistantRunResponse(
        finalText: 'ok',
        traces: <AssistantTraceEvent>[
          AssistantTraceEvent(
            type: AssistantTraceEventType.lifecycleStart,
            message: 'start',
            timestamp: DateTime.parse('2026-01-01T00:00:00Z'),
            data: const <String, dynamic>{'k': 'v'},
          ),
        ],
        degraded: true,
        errorCode: 'network_unavailable',
      );
      final decoded = AssistantRunResponse.fromJson(response.toJson());
      expect(decoded.finalText, equals('ok'));
      expect(decoded.degraded, isTrue);
      expect(decoded.errorCode, equals('network_unavailable'));
      expect(decoded.traces.first.type, equals(AssistantTraceEventType.lifecycleStart));
      expect(decoded.traces.first.data?['k'], equals('v'));
    });

    test('tool result supports unified fields', () {
      const result = AssistantToolResult(
        success: false,
        message: 'failed',
        errorCode: AssistantErrorCode.executionFailed,
        degraded: true,
      );
      final decoded = AssistantToolResult.fromJson(result.toJson());
      expect(decoded.success, isFalse);
      expect(decoded.errorCode, equals(AssistantErrorCode.executionFailed));
      expect(decoded.degraded, isTrue);
    });
  });
}
