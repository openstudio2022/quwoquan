// 会话首屏性能观测契约：requested→ready 上报一次 performance_sample，
// payload 与 telemetry codegen 契约同源，同一次打开不重复上报。
//
// spec_ref: specs/feature-tree/chat-conversation/message-reliability-foundation/message-runtime-performance-budget/spec.md#gwt-002.t3
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/observability/trackers/chat_conversation_performance_observability.dart';

import '../../../../support/runtime/observability/recording_app_telemetry_recorder.dart';

void main() {
  late RecordingAppTelemetryRecorder ops;
  late ChatConversationPerformanceObservability observability;

  setUp(() {
    ops = RecordingAppTelemetryRecorder();
    observability = ChatConversationPerformanceObservability(telemetry: ops);
  });

  List<RecordedAppTelemetry> ttiEvents() {
    return ops.recorded
        .where(
          (event) =>
              event.extensions['operationId'] ==
              ChatConversationPerformanceMetricNames.firstScreenTtiMs,
        )
        .toList();
  }

  test('打开 -> 首屏就绪 上报一次会话首屏采样且 payload 同源', () async {
    observability.markConversationOpened('conv-1');
    observability.markFirstTimelineReady('conv-1', messageCount: 20);

    final events = ttiEvents();
    expect(events, hasLength(1));
    expect(events.first.eventType, 'performance_sample');
    expect(events.first.extensions['durationMs'], isA<int>());
    expect((events.first.extensions['durationMs']! as int) >= 0, isTrue);
    expect(events.first.extensions['result'], 'ok');
  });

  test('未先标记打开时首屏就绪不上报（无计时起点）', () async {
    observability.markFirstTimelineReady('conv-1', messageCount: 5);
    expect(ttiEvents(), isEmpty);
  });

  test('同一会话重复就绪只上报一次', () async {
    observability.markConversationOpened('conv-1');
    observability.markFirstTimelineReady('conv-1', messageCount: 20);
    observability.markConversationOpened('conv-1');
    observability.markFirstTimelineReady('conv-1', messageCount: 30);

    expect(ttiEvents(), hasLength(1));
  });

  test('resetConversation 后再次打开可重新上报', () async {
    observability.markConversationOpened('conv-1');
    observability.markFirstTimelineReady('conv-1', messageCount: 20);
    observability.resetConversation('conv-1');
    observability.markConversationOpened('conv-1');
    observability.markFirstTimelineReady('conv-1', messageCount: 8);

    expect(ttiEvents(), hasLength(2));
  });

  test('空白会话 ID 与负数消息数被忽略', () async {
    observability.markConversationOpened('   ');
    observability.markFirstTimelineReady('   ', messageCount: 3);
    observability.markConversationOpened('conv-2');
    observability.markFirstTimelineReady('conv-2', messageCount: -1);

    expect(ttiEvents(), isEmpty);
  });
}
