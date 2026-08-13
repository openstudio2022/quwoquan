// spec_ref: specs/feature-tree/chat-conversation/realtime-call/spec.md#sit-008
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/call-experience/spec.md#gwt-003
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/call-experience/spec.md#gwt-005
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/spec.md#sit-005.t4
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/spec.md#sit-008.t4
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/call-experience/spec.md#gwt-003.t1
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('RTC 屏幕共享轨道经平台边界进入参与者模型并由视频页真实渲染', () {
    final participantsProvider = File(
      'lib/service/rtc_service/rtc/call_session/application/call_participants_provider.dart',
    ).readAsStringSync();
    final participantModel = File(
      'lib/service/rtc_service/rtc/call_session/domain/call_participant.dart',
    ).readAsStringSync();
    final videoPage = File(
      'lib/service/rtc_service/rtc/call_session/presentation/video_call_page.dart',
    ).readAsStringSync();
    final shareSurface = File(
      'lib/service/rtc_service/rtc/call_session/presentation/video_call_screen_share_surface.dart',
    ).readAsStringSync();

    expect(
      participantsProvider,
      contains('screenShareTrack: participant.screenShareTrack'),
    );
    expect(
      participantsProvider,
      contains('screenShareTrack: current.screenShareTrack'),
    );
    expect(participantsProvider, contains('clearScreenShareTrack:'));
    expect(participantModel, contains('final RtcVideoTrack? screenShareTrack'));
    expect(videoPage, contains('participant.hasScreenShareTrack'));
    expect(videoPage, contains('track: sharer?.screenShareTrack'));
    expect(shareSurface, contains('RtcVideoTrackRenderer('));
    expect(shareSurface, contains('CallText.callScreenShareConnecting'));
  });
}
