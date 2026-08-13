// spec_ref: specs/feature-tree/chat-conversation/realtime-call/call-experience/spec.md#gwt-009
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/call-experience/spec.md#gwt-009.t1
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/call-experience/spec.md#gwt-009.t2
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/call-experience/spec.md#gwt-009.t3
//
// RTC 音频会话与中断处理契约：
// 媒体连通后必须以通话配置激活音频会话；收尾必须释放。系统中断 began
// 本地静音采集，ended(shouldResume) 在用户未主动静音时恢复；
// becomingNoisy（耳机拔出）从扬声器切回听筒防外放。
import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/platform/call_audio_session_gateway.dart';
import 'package:quwoquan_app/runtime/platform/platform_providers.dart';
import 'package:quwoquan_app/runtime/platform/rtc_room_service.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/call_session_provider.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/media_device_provider.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/rtc_service/rtc/call_session/call_session_typed_double.dart';

/// CallSessionTypedDouble seed：音频通话（来电方）。
const String _seedAudioCallId = '11111111-1111-4111-8111-111111111111';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  (ProviderContainer, _RecordingCallAudioGateway, _RecordingRtcRoomService)
  createHarness() {
    final gateway = _RecordingCallAudioGateway();
    final room = _RecordingRtcRoomService();
    final callSessions = CallSessionTypedDouble();
    final container = ProviderContainer(
      overrides: [
        callAudioSessionGatewayProvider.overrideWithValue(gateway),
        rtcRoomServiceProvider.overrideWithValue(room),
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
    return (container, gateway, room);
  }

  Future<void> answerSeedCall(ProviderContainer container) async {
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
    await Future<void>.delayed(Duration.zero);
  }

  test('媒体连通激活音频会话，收尾释放', () async {
    final (container, gateway, _) = createHarness();
    await answerSeedCall(container);

    expect(gateway.activateCount, 1, reason: '接听建连后必须激活通话音频会话');
    expect(gateway.deactivateCount, 0);

    await container.read(callSessionProvider.notifier).hangupCall();
    await Future<void>.delayed(Duration.zero);
    expect(gateway.deactivateCount, greaterThanOrEqualTo(1), reason: '收尾必须释放音频会话');
  });

  test('中断 began 本地静音，ended(shouldResume) 恢复采集', () async {
    final (container, gateway, room) = createHarness();
    await answerSeedCall(container);
    room.micValues.clear();

    gateway.emit(CallAudioSessionEvent.interruptionBegan);
    await Future<void>.delayed(Duration.zero);
    expect(room.micValues, [false], reason: '中断开始必须本地静音采集');

    gateway.emit(CallAudioSessionEvent.interruptionEndedShouldResume);
    await Future<void>.delayed(Duration.zero);
    expect(room.micValues, [false, true], reason: '中断结束建议恢复时必须恢复采集');
  });

  test('用户主动静音时中断恢复不得擅自取消静音', () async {
    final (container, gateway, room) = createHarness();
    await answerSeedCall(container);
    final notifier = container.read(callSessionProvider.notifier);

    await notifier.toggleMute();
    expect(container.read(callSessionProvider).isMuted, isTrue);
    room.micValues.clear();

    gateway.emit(CallAudioSessionEvent.interruptionBegan);
    gateway.emit(CallAudioSessionEvent.interruptionEndedShouldResume);
    await Future<void>.delayed(Duration.zero);
    expect(
      room.micValues,
      isEmpty,
      reason: '用户主动静音期间中断往返不得改动采集状态',
    );
  });

  test('becomingNoisy 从扬声器切回听筒防外放', () async {
    final (container, gateway, room) = createHarness();
    await answerSeedCall(container);
    final mediaDevice = container.read(mediaDeviceProvider.notifier);
    await mediaDevice.setAudioOutput(AudioOutput.speaker);
    expect(container.read(mediaDeviceProvider).audioOutput, AudioOutput.speaker);
    room.speakerValues.clear();

    gateway.emit(CallAudioSessionEvent.becameNoisy);
    await Future<void>.delayed(Duration.zero);

    expect(
      container.read(mediaDeviceProvider).audioOutput,
      AudioOutput.earpiece,
      reason: '耳机拔出必须切回听筒',
    );
    expect(room.speakerValues, [false]);
  });

  test('听筒态 becomingNoisy 不重复切换', () async {
    final (container, gateway, room) = createHarness();
    await answerSeedCall(container);
    room.speakerValues.clear();

    gateway.emit(CallAudioSessionEvent.becameNoisy);
    await Future<void>.delayed(Duration.zero);
    expect(room.speakerValues, isEmpty);
  });
}

final class _RecordingCallAudioGateway implements CallAudioSessionGateway {
  int activateCount = 0;
  int deactivateCount = 0;
  final StreamController<CallAudioSessionEvent> _controller =
      StreamController<CallAudioSessionEvent>.broadcast();

  void emit(CallAudioSessionEvent event) => _controller.add(event);

  @override
  Future<bool> activateForCall() async {
    activateCount += 1;
    return true;
  }

  @override
  Future<void> deactivate() async {
    deactivateCount += 1;
  }

  @override
  Stream<CallAudioSessionEvent> get events => _controller.stream;
}

final class _RecordingRtcRoomService extends RtcRoomService {
  final List<bool> micValues = <bool>[];
  final List<bool> speakerValues = <bool>[];

  @override
  Future<void> connect({
    required String accessToken,
    bool enableVideo = false,
    bool enableAudio = true,
  }) async {}

  @override
  Future<void> disconnect() async {}

  @override
  Future<void> setMicrophoneEnabled(bool enabled) async {
    micValues.add(enabled);
  }

  @override
  Future<void> setSpeakerOn(bool speakerOn) async {
    speakerValues.add(speakerOn);
  }

  @override
  void dispose() {}
}
