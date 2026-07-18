/// user_acceptance Patrol：环境注入的视频播放 canary。
library;

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/core/testing/patrol_test_support.dart';

const _videoWorkId = String.fromEnvironment('VIDEO_PLAYBACK_CANARY_WORK_ID');
const _videoProbeKeys = <ValueKey<String>>[
  ValueKey<String>('works-video-stage-$_videoWorkId-0'),
  ValueKey<String>('works-video-$_videoWorkId-0'),
  ValueKey<String>('home-video-player-$_videoWorkId'),
];

void main() {
  patrolTest(
    'environment_video_playback_canary',
    tags: ['t4', 'environment-smoke', 'video-playback'],
    skip: !kRunPatrolT4,
    config: PatrolTesterConfig(
      visibleTimeout: const Duration(seconds: 12),
      printLogs: true,
    ),
    ($) async {
      await launchPatrolAppOnce($);
      expect(
        _videoWorkId.trim(),
        isNotEmpty,
        reason:
            'environment Patrol requires an injected video playback canary work id',
      );

      await patrolGoTo(
        $,
        AppRoutePaths.workBrowser(
          workId: _videoWorkId,
          source: 'environmentVideoPlaybackCanary',
        ),
      );
      final videoStageKey = await _waitForAnyKey($, _videoProbeKeys);
      expect(
        videoStageKey,
        isNotNull,
        reason: 'configured video canary stage should render',
      );
      await $(find.byKey(videoStageKey!)).tap();
      await $.pump(const Duration(milliseconds: 500));
      final playerReady = await _waitForAnyKey($, const <ValueKey<String>>[
        ValueKey<String>('video-player-ready'),
      ]);
      final playerError = find
          .byKey(const ValueKey<String>('video-player-error'))
          .evaluate()
          .isNotEmpty;
      expect(
        playerReady,
        isNotNull,
        reason: playerError
            ? 'native video player entered its explicit error state'
            : 'native video player must reach ready state',
      );
      expect(
        find.byKey(const ValueKey<String>('video-player-error')).evaluate(),
        isEmpty,
        reason: 'configured video canary must not enter the error state',
      );
    },
  );
}

Future<Key?> _waitForAnyKey(
  PatrolIntegrationTester $,
  Iterable<Key> keys, {
  Duration timeout = const Duration(seconds: 60),
}) async {
  final deadline = DateTime.now().add(timeout);
  while (DateTime.now().isBefore(deadline)) {
    for (final key in keys) {
      if (find.byKey(key).evaluate().isNotEmpty) {
        return key;
      }
    }
    await $.pump(const Duration(milliseconds: 500));
  }
  return null;
}
