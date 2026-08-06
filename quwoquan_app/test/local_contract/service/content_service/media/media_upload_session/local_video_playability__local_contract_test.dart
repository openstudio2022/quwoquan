import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/adapters/local_video_file_readiness.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/local_video_playability.dart';

void main() {
  test(
    'DefaultLocalVideoPlayability delegates the canonical path once',
    () async {
      final paths = <String>[];
      final LocalVideoPlayability playability = DefaultLocalVideoPlayability(
        waiter: (path) async => paths.add(path),
      );

      await playability.waitUntilPlayable('/tmp/video.mp4');

      expect(paths, <String>['/tmp/video.mp4']);
    },
  );

  test('DefaultLocalVideoPlayability preserves readiness failures', () async {
    final playability = DefaultLocalVideoPlayability(
      waiter: (_) => Future<void>.error(StateError('not playable')),
    );

    await expectLater(
      playability.waitUntilPlayable('/tmp/broken.mp4'),
      throwsA(isA<StateError>()),
    );
  });
}
