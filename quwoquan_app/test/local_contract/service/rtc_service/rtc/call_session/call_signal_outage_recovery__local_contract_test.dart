// spec_ref: specs/feature-tree/chat-conversation/realtime-call/spec.md#sit-007
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/spec.md#sit-007.t3
//
// 前后台/信令通道中断恢复契约：
// App 进后台或网络闪断时 realtime 通道断开，期间的通话信令（对端挂断、
// 参与者变化）会丢失；通道恢复后 CallSession 必须从 CallQuery 对齐事实，
// 不得让回前台的用户停留在过期的本地通话状态。
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/platform/rtc_room_service.dart';
import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/application/realtime_connection_notifier.dart';
import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/application/public/realtime_connection_delegate.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/active_call_service.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/call_session_provider.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/rtc_service/rtc/call_session/call_session_typed_double.dart';

const String _seedCallId = '11111111-1111-4111-8111-111111111111';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  (ProviderContainer, _ManualRealtimeConnectionNotifier)
  createHarness({required CallQuery query}) {
    final realtime = _ManualRealtimeConnectionNotifier();
    final container = ProviderContainer(
      overrides: [
        rtcCallQueryProvider.overrideWith((ref, surface) => query),
        realtimeConnectionManagerProvider.overrideWith(() => realtime),
        rtcRoomServiceProvider.overrideWithValue(_NoopRtcRoomService()),
      ],
    );
    addTearDown(container.dispose);
    return (container, realtime);
  }

  Future<void> pumpEventQueue() async {
    for (var i = 0; i < 4; i++) {
      await Future<void>.delayed(Duration.zero);
    }
  }

  test('通话中通道恢复后从 CallQuery 对齐对端挂断事实并收尾', () async {
    final callSessions = CallSessionTypedDouble();
    await callSessions.answerCall(RtcCallIdCommand(callId: _seedCallId));
    final query = _RecordingCallQuery(callSessions);
    final (container, realtime) = createHarness(query: query);

    final notifier = container.read(callSessionProvider.notifier);
    notifier.loadFromSession(
      await callSessions.getCall(RtcGetCallQuery(callId: _seedCallId)),
    );
    container
        .read(activeCallProvider.notifier)
        .startCall(callId: _seedCallId, callType: 'audio');
    expect(container.read(callSessionProvider).status, CallStatus.inCall);

    // 通道断开期间对端挂断（事件丢失，本地不知情）。
    realtime.setTransport(TransportState.disconnected);
    await callSessions.hangupCall(RtcCallIdCommand(callId: _seedCallId));
    expect(container.read(callSessionProvider).status, CallStatus.inCall);

    // 回前台/重连：通道恢复触发 CallQuery 对齐，本地必须收尾。
    realtime.setTransport(TransportState.idle);
    await pumpEventQueue();

    final state = container.read(callSessionProvider);
    expect(state.status, CallStatus.ended, reason: '错过的挂断事实必须在通道恢复后补偿');
    expect(state.session?.endReason, EndReason.normal);
    expect(container.read(activeCallProvider).isInCall, isFalse);
    expect(query.getCallCount, greaterThanOrEqualTo(1));
  });

  test('通话事实未变时通道恢复只刷新聚合不产生失败或状态回退', () async {
    final callSessions = CallSessionTypedDouble();
    await callSessions.answerCall(RtcCallIdCommand(callId: _seedCallId));
    final query = _RecordingCallQuery(callSessions);
    final (container, realtime) = createHarness(query: query);

    final notifier = container.read(callSessionProvider.notifier);
    notifier.loadFromSession(
      await callSessions.getCall(RtcGetCallQuery(callId: _seedCallId)),
    );

    realtime.setTransport(TransportState.disconnected);
    realtime.setTransport(TransportState.active);
    await pumpEventQueue();

    final state = container.read(callSessionProvider);
    expect(state.status, CallStatus.inCall);
    expect(state.failure, isNull);
    expect(query.getCallCount, greaterThanOrEqualTo(1));
  });

  test('无活跃通话时通道恢复不触发通话查询', () async {
    final query = _RecordingCallQuery(CallSessionTypedDouble());
    final (container, realtime) = createHarness(query: query);
    container.read(callSessionProvider.notifier);

    realtime.setTransport(TransportState.disconnected);
    realtime.setTransport(TransportState.idle);
    await pumpEventQueue();

    expect(query.getCallCount, 0);
  });

  test('通话已本地收尾后通道恢复不再查询', () async {
    final callSessions = CallSessionTypedDouble();
    await callSessions.hangupCall(RtcCallIdCommand(callId: _seedCallId));
    final query = _RecordingCallQuery(callSessions);
    final (container, realtime) = createHarness(query: query);

    final notifier = container.read(callSessionProvider.notifier);
    notifier.loadFromSession(
      await callSessions.getCall(RtcGetCallQuery(callId: _seedCallId)),
    );
    expect(container.read(callSessionProvider).status, CallStatus.ended);

    realtime.setTransport(TransportState.disconnected);
    realtime.setTransport(TransportState.idle);
    await pumpEventQueue();

    expect(query.getCallCount, 0);
  });
}

final class _RecordingCallQuery implements CallQuery {
  _RecordingCallQuery(this._inner);

  final CallSessionTypedDouble _inner;
  int getCallCount = 0;

  @override
  Future<CallSession> getCall(RtcGetCallQuery query) {
    getCallCount += 1;
    return _inner.getCall(query);
  }

  @override
  Future<RtcCallHistoryPage> listCalls(RtcListCallsQuery query) =>
      _inner.listCalls(query);
}

class _ManualRealtimeConnectionNotifier extends RealtimeConnectionNotifier {
  _ManualRealtimeConnectionNotifier()
    : super(
        delegateFactory:
            ({
              required ref,
              required onStateChanged,
              required currentUserIdResolver,
            }) => throw StateError('overridden build must not create delegate'),
      );

  @override
  TransportState build() => TransportState.idle;

  void setTransport(TransportState next) {
    state = next;
  }

  @override
  void onAppForeground() {}

  @override
  void onAppBackground() {}
}

final class _NoopRtcRoomService extends RtcRoomService {
  @override
  Future<void> connect({
    required String accessToken,
    bool enableVideo = false,
    bool enableAudio = true,
  }) async {}

  @override
  Future<void> disconnect() async {}

  @override
  void dispose() {}
}
