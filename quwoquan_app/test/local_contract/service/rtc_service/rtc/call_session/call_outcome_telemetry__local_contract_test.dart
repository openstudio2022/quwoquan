// spec_ref: specs/feature-tree/chat-conversation/realtime-call/call-experience/spec.md#gwt-010
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/call-experience/spec.md#gwt-010.t1
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/call-experience/spec.md#gwt-010.t2
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/call-experience/spec.md#gwt-010.t3
//
// rtc_call_outcome 结局粒度契约：
// 运营漏斗要求 completed/rejected/cancelled/no_answer/failed 五种结局可
// 区分；结局以服务端 endReason 事实为准，禁止把拒接/取消/超时合并归因。
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/observability/generated/app_telemetry_catalog.g.dart';
import 'package:quwoquan_app/runtime/observability/telemetry/app_telemetry_outbox.dart';
import 'package:quwoquan_app/runtime/observability/telemetry/app_telemetry_reporter.dart';
import 'package:quwoquan_app/runtime/platform/rtc_room_service.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/call_session_provider.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/rtc_signal_events.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/rtc_service/rtc/call_session/call_session_typed_double.dart';

/// CallSessionTypedDouble seed：音频来电。
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

  void seedRinging(ProviderContainer container) {
    container
        .read(callSessionProvider.notifier)
        .seedIncomingCall(
          callId: _seedAudioCallId,
          callType: 'audio',
          initiatorId: 'user-caller',
          callerName: 'Caller',
          expiresAt: DateTime.now()
              .toUtc()
              .add(const Duration(minutes: 1))
              .toIso8601String(),
        );
  }

  test('接听后挂断上报 completed', () async {
    final (container, recorder, _) = createHarness();
    seedRinging(container);
    final notifier = container.read(callSessionProvider.notifier);
    await notifier.answerCall(_seedAudioCallId);
    await notifier.hangupCall();
    await Future<void>.delayed(Duration.zero);

    expect(recorder.outcomes, ['completed']);
  });

  test('来电拒接上报 rejected', () async {
    final (container, recorder, _) = createHarness();
    seedRinging(container);
    await container
        .read(callSessionProvider.notifier)
        .rejectCall(_seedAudioCallId);
    await Future<void>.delayed(Duration.zero);

    expect(recorder.outcomes, ['rejected'], reason: '拒接不得归因为 cancelled');
  });

  test('主叫取消上报 cancelled', () async {
    final (container, recorder, callSessions) = createHarness();
    final notifier = container.read(callSessionProvider.notifier);
    notifier.loadFromSession(
      await callSessions.getCall(RtcGetCallQuery(callId: _seedAudioCallId)),
    );
    await notifier.cancelCall();
    await Future<void>.delayed(Duration.zero);

    expect(recorder.outcomes, ['cancelled']);
  });

  test('服务端 no_answer 超时信令上报 no_answer', () async {
    final (container, recorder, _) = createHarness();
    seedRinging(container);

    container.read(rtcSignalEventBusProvider).emit(
      RealtimeEventEnvelope.fromWire(<String, Object?>{
        'type': 'call.ended',
        'occurredAt': '2026-08-04T10:00:00Z',
        'payload': <String, Object?>{
          'callId': _seedAudioCallId,
          'endReason': 'no_answer',
        },
      }),
    );
    await Future<void>.delayed(Duration.zero);

    expect(
      recorder.outcomes,
      ['no_answer'],
      reason: '超时未接必须与主动取消可区分',
    );
  });

  test('服务端 error 收尾信令上报 failed', () async {
    final (container, recorder, _) = createHarness();
    seedRinging(container);

    container.read(rtcSignalEventBusProvider).emit(
      RealtimeEventEnvelope.fromWire(<String, Object?>{
        'type': 'call.ended',
        'occurredAt': '2026-08-04T10:00:00Z',
        'payload': <String, Object?>{
          'callId': _seedAudioCallId,
          'endReason': 'error',
        },
      }),
    );
    await Future<void>.delayed(Duration.zero);

    expect(recorder.outcomes, ['failed']);
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
