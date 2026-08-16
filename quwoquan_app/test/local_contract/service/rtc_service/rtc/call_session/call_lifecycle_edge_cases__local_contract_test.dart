// spec_ref: specs/feature-tree/chat-conversation/realtime-call/spec.md#sit-007.t5
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/one-to-one-call/spec.md#gwt-003
//
// 通话生命周期边界契约：
// - PiP enter→exit→re-enter 状态往返不丢失通话事实。
// - 本地挂断与对端 `call.ended` 双发竞态只收尾一次（outcome 只发一次、
//   activeCall 清理幂等）。
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/observability/generated/app_telemetry_catalog.g.dart';
import 'package:quwoquan_app/runtime/observability/telemetry/app_telemetry_outbox.dart';
import 'package:quwoquan_app/runtime/observability/telemetry/app_telemetry_reporter.dart';
import 'package:quwoquan_app/runtime/platform/rtc_room_service.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/active_call_service.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/call_session_provider.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/rtc_signal_events.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/rtc_service/rtc/call_session/call_session_typed_double.dart';

const String _seedAudioCallId = '11111111-1111-4111-8111-111111111111';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  (ProviderContainer, _RecordingTelemetryRecorder, CallSessionTypedDouble)
  createHarness() {
    final recorder = _RecordingTelemetryRecorder();
    final callSessions = CallSessionTypedDouble();
    final container = ProviderContainer(
      overrides: [
        appTelemetryReporterProvider.overrideWithValue(recorder),
        rtcRoomServiceProvider.overrideWithValue(_NoopRtcRoomService()),
        rtcCallQueryProvider.overrideWith((ref, surface) => callSessions),
        rtcCallLifecycleCommandWriterProvider.overrideWith(
          (ref, surface) => callSessions,
        ),
        rtcCallParticipantCommandWriterProvider.overrideWith(
          (ref, surface) => callSessions,
        ),
        rtcCallMediaControlWriterProvider.overrideWith(
          (ref, surface) => callSessions,
        ),
      ],
    );
    addTearDown(container.dispose);
    return (container, recorder, callSessions);
  }

  test('PiP enter→exit→re-enter 往返不丢通话事实', () {
    final (container, _, _) = createHarness();
    final activeCall = container.read(activeCallProvider.notifier);
    activeCall.startCall(callId: _seedAudioCallId, callType: 'audio');

    activeCall.enterPipMode();
    var state = container.read(activeCallProvider);
    expect(state.isPipMode, isTrue);
    expect(state.isInCall, isTrue);

    activeCall.exitPipMode();
    state = container.read(activeCallProvider);
    expect(state.isPipMode, isFalse);
    expect(state.isInCall, isTrue, reason: '退出 PiP 不得终结通话');
    expect(state.callId, _seedAudioCallId);

    activeCall.enterPipMode();
    state = container.read(activeCallProvider);
    expect(state.isPipMode, isTrue);
    expect(state.callId, _seedAudioCallId, reason: '再入 PiP 保持同一通话');

    activeCall.endCall();
    expect(container.read(activeCallProvider).isInCall, isFalse);
  });

  test('通话结束后 enterPipMode 不得复活 PiP', () {
    final (container, _, _) = createHarness();
    final activeCall = container.read(activeCallProvider.notifier);
    activeCall.startCall(callId: _seedAudioCallId, callType: 'audio');
    activeCall.endCall();

    activeCall.enterPipMode();
    expect(container.read(activeCallProvider).isPipMode, isFalse);
  });

  test('本地挂断与对端 call.ended 双发竞态只收尾一次', () async {
    final (container, recorder, callSessions) = createHarness();
    final notifier = container.read(callSessionProvider.notifier);
    notifier.seedIncomingCall(
      callId: _seedAudioCallId,
      callType: 'audio',
      initiatorId: 'user-caller',
      callerName: 'Caller',
      expiresAt: DateTime.now()
          .toUtc()
          .add(const Duration(minutes: 1))
          .toIso8601String(),
    );
    await notifier.answerCall(_seedAudioCallId);

    // 双发：本地挂断已提交，同时对端 call.ended 信令到达。
    final hangup = notifier.hangupCall();
    container
        .read(rtcSignalEventBusProvider)
        .emit(
          RealtimeEventEnvelope.fromWire(<String, Object?>{
            'type': 'call.ended',
            'occurredAt': '2026-08-04T10:00:00Z',
            'payload': <String, Object?>{
              'callId': _seedAudioCallId,
              'endReason': 'normal',
            },
          }),
        );
    await hangup;
    await Future<void>.delayed(Duration.zero);

    final state = container.read(callSessionProvider);
    expect(state.status, CallStatus.ended);
    expect(
      recorder.outcomes,
      hasLength(1),
      reason: '双发竞态下 rtc_call_outcome 只能发射一次',
    );
    expect(recorder.outcomes.single, 'completed');
    expect(container.read(activeCallProvider).isInCall, isFalse);
  });
}

final class _RecordingTelemetryRecorder implements AppTelemetryRecorder {
  final List<AppTelemetryPayload> payloads = <AppTelemetryPayload>[];

  List<String> get outcomes => payloads
      .where((payload) => payload.eventType == 'rtc_call_outcome')
      .map((payload) => payload.extensions['result']! as String)
      .toList();

  @override
  Future<AppTelemetryRecordResult> record(
    AppTelemetryPayload payload, {
    String? pageName,
    DateTime? occurredAt,
  }) async {
    payloads.add(payload);
    return AppTelemetryRecordResult.accepted;
  }

  @override
  Future<AppTelemetryFlushResult> flush() async =>
      AppTelemetryFlushResult.empty;

  @override
  Future<void> clearPendingForLogout() async {}

  @override
  void onNetworkAvailable() {}
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
