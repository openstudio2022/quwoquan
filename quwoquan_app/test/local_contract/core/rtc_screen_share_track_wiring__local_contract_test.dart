import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('LiveKit screen-share-video 轨道进入参与者模型并由视频页真实渲染', () {
    final participantsProvider = File(
      'lib/ui/rtc/providers/call_participants_provider.dart',
    ).readAsStringSync();
    final participantModel = File(
      'lib/ui/rtc/models/call_participant.dart',
    ).readAsStringSync();
    final videoPage = File(
      'lib/ui/rtc/pages/video_call_page.dart',
    ).readAsStringSync();
    final shareSurface = File(
      'lib/ui/rtc/widgets/video_call_screen_share_surface.dart',
    ).readAsStringSync();

    expect(participantsProvider, contains('lk.TrackSource.screenShareVideo'));
    expect(
      participantsProvider,
      contains('screenShareTrack: screenShareTrack'),
    );
    expect(
      participantsProvider,
      contains('screenShareTrack: current.screenShareTrack'),
    );
    expect(participantsProvider, contains('clearScreenShareTrack:'));
    expect(participantModel, contains('final VideoTrack? screenShareTrack'));
    expect(videoPage, contains('participant.hasScreenShareTrack'));
    expect(videoPage, contains('track: sharer?.screenShareTrack'));
    expect(
      shareSurface,
      contains('VideoTrackRenderer(activeTrack, fit: VideoViewFit.contain)'),
    );
    expect(shareSurface, contains('UITextConstants.callScreenShareConnecting'));
  });
}
