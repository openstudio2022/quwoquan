// spec_ref: specs/feature-tree/chat-conversation/realtime-call/spec.md#sit-007.t4
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/call-experience/spec.md#gwt-004
//
// 控制条按钮 → 应用层 → SFU 全链路契约：
// 点击翻转摄像头/扬声器按钮必须经 mediaDeviceProvider 真实到达 SFU
// （switchCamera / setSpeakerOn），且 UI 状态与设备状态同步推进。
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/platform/rtc_room_service.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/call_session_provider.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/media_device_provider.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/presentation/call_controls_bar.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/rtc_service/rtc/call_session/call_session_typed_double.dart';

/// CallSessionTypedDouble seed 中的 video 会话。
const String _seedVideoCallId = '22222222-2222-4222-8222-222222222222';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  Future<(ProviderContainer, _RecordingRtcRoomService)> pumpControls(
    WidgetTester tester,
  ) async {
    final room = _RecordingRtcRoomService();
    final callSessions = CallSessionTypedDouble();
    await callSessions.answerCall(RtcCallIdCommand(callId: _seedVideoCallId));
    final container = ProviderContainer(
      overrides: [rtcRoomServiceProvider.overrideWithValue(room)],
    );
    addTearDown(container.dispose);
    container
        .read(callSessionProvider.notifier)
        .loadFromSession(
          await callSessions.getCall(RtcGetCallQuery(callId: _seedVideoCallId)),
        );
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: MaterialApp(
          builder: (context, child) => MediaQuery(
            data: const MediaQueryData(size: Size(1200, 800)),
            child: child!,
          ),
          home: Scaffold(
            body: SizedBox(
              width: 1200,
              height: 200,
              child: CallControlsBar(
                callType: CallType.video,
                onHangup: () {},
                autoHide: false,
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pump();
    return (container, room);
  }

  testWidgets('点击翻转摄像头按钮真实到达 SFU switchCamera 并翻转设备位姿', (tester) async {
    final (container, room) = await pumpControls(tester);
    expect(
      container.read(mediaDeviceProvider).cameraPosition,
      CameraPosition.front,
    );

    await tester.tap(find.byIcon(CupertinoIcons.switch_camera));
    await tester.pump();

    expect(room.switchCameraCount, 1, reason: '翻转必须到达 SFU 层');
    expect(
      container.read(mediaDeviceProvider).cameraPosition,
      CameraPosition.back,
      reason: '设备位姿必须随成功翻转推进（镜像决策依赖它）',
    );
  });

  testWidgets('点击扬声器按钮真实到达 SFU setSpeakerOn 并同步输出状态', (tester) async {
    final (container, room) = await pumpControls(tester);
    expect(
      container.read(mediaDeviceProvider).audioOutput,
      AudioOutput.earpiece,
    );

    await tester.tap(find.byIcon(CupertinoIcons.speaker_1));
    await tester.pump();

    expect(room.speakerValues, [true], reason: '扬声器开必须到达 SFU 层');
    expect(
      container.read(mediaDeviceProvider).audioOutput,
      AudioOutput.speaker,
    );

    await tester.tap(find.byIcon(CupertinoIcons.speaker_2_fill));
    await tester.pump();
    expect(room.speakerValues, [true, false], reason: '再点必须切回听筒');
    expect(
      container.read(mediaDeviceProvider).audioOutput,
      AudioOutput.earpiece,
    );
  });

  testWidgets('SFU 翻转失败时设备位姿不得伪推进', (tester) async {
    final (container, room) = await pumpControls(tester);
    room.shouldFail = true;

    await tester.tap(find.byIcon(CupertinoIcons.switch_camera));
    await tester.pump();

    expect(
      container.read(mediaDeviceProvider).cameraPosition,
      CameraPosition.front,
      reason: 'SFU 失败时不得伪报翻转成功',
    );
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
