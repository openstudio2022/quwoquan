// spec_ref: specs/feature-tree/chat-conversation/realtime-call/spec.md#sit-007.t4
//
// 通话中媒体控制真实生效契约：
// 翻转摄像头必须调用 SFU switchCamera、音频输出必须调用 setSpeakerOn；
// 失败时返回 false 并暴露结构化 failure，不得伪报成功或吞掉错误。
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/platform/rtc_room_service.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/call_session_provider.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/rtc_service/rtc/call_session/call_session_typed_double.dart';

/// CallSessionTypedDouble seed 中的 video 会话：接听后 isCameraOn 为 true。
const String _seedCallId = '22222222-2222-4222-8222-222222222222';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  (ProviderContainer, _RecordingRtcRoomService) createHarness() {
    final room = _RecordingRtcRoomService();
    final container = ProviderContainer(
      overrides: [rtcRoomServiceProvider.overrideWithValue(room)],
    );
    addTearDown(container.dispose);
    return (container, room);
  }

  Future<void> loadInCallVideoSession(ProviderContainer container) async {
    final callSessions = CallSessionTypedDouble();
    await callSessions.answerCall(RtcCallIdCommand(callId: _seedCallId));
    final notifier = container.read(callSessionProvider.notifier);
    notifier.loadFromSession(
      await callSessions.getCall(RtcGetCallQuery(callId: _seedCallId)),
    );
  }

  test('翻转摄像头调用 SFU switchCamera 并在成功后清除失败态', () async {
    final (container, room) = createHarness();
    await loadInCallVideoSession(container);
    final notifier = container.read(callSessionProvider.notifier);
    expect(container.read(callSessionProvider).isCameraOn, isTrue);

    expect(await notifier.switchCamera(), isTrue);
    expect(room.switchCameraCount, 1, reason: '翻转必须真实到达 SFU 层');
    expect(container.read(callSessionProvider).failure, isNull);
  });

  test('扬声器切换调用 setSpeakerOn 且开关值透传', () async {
    final (container, room) = createHarness();
    await loadInCallVideoSession(container);
    final notifier = container.read(callSessionProvider.notifier);

    expect(await notifier.setSpeakerOn(true), isTrue);
    expect(await notifier.setSpeakerOn(false), isTrue);
    expect(room.speakerValues, [true, false]);
  });

  test('SFU 控制失败返回 false 并暴露结构化 failure，不伪报成功', () async {
    final (container, room) = createHarness();
    room.shouldFail = true;
    await loadInCallVideoSession(container);
    final notifier = container.read(callSessionProvider.notifier);

    expect(await notifier.setSpeakerOn(true), isFalse);
    final state = container.read(callSessionProvider);
    expect(state.failure, isNotNull);
  });
}

final class _RecordingRtcRoomService extends RtcRoomService {
  int switchCameraCount = 0;
  final List<bool> speakerValues = <bool>[];
  bool shouldFail = false;

  @override
  Future<void> connect({
    required String accessToken,
    bool enableVideo = false,
    bool enableAudio = true,
  }) async {}

  @override
  Future<void> disconnect() async {}

  @override
  Future<void> switchCamera() async {
    if (shouldFail) throw StateError('fixture switch camera failure');
    switchCameraCount += 1;
  }

  @override
  Future<void> setSpeakerOn(bool speakerOn) async {
    if (shouldFail) throw StateError('fixture speaker failure');
    speakerValues.add(speakerOn);
  }

  @override
  void dispose() {}
}
