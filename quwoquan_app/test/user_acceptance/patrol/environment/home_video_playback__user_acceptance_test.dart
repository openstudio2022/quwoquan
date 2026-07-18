/// user_acceptance Patrol：alpha 首页两张视频卡的原生自动播放验收。
library;

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/core/testing/patrol_test_support.dart';

const _homeVideoPostIds = <String>[
  'alpha_video_portrait_playable',
  'alpha_video_landscape_playable',
];
const _feedKey = ValueKey<String>('home-feed-recommend');
const _readyKey = ValueKey<String>('video-player-ready');
const _errorKey = ValueKey<String>('video-player-error');

void main() {
  patrolTest(
    'environment_home_video_playback',
    tags: ['t4', 'environment-smoke', 'video-playback'],
    skip: !kRunPatrolT4,
    config: PatrolTesterConfig(
      visibleTimeout: const Duration(seconds: 12),
      printLogs: true,
    ),
    ($) async {
      await launchPatrolAppOnce($);
      await patrolGoTo($, AppRoutePaths.home);

      for (final postId in _homeVideoPostIds) {
        final reachedReady = await _focusVideoCardAndWaitForReady($, postId);
        expect(reachedReady, isTrue, reason: '首页视频 $postId 应在稳定可见后完成原生播放器初始化');
        expect(
          find.byKey(_errorKey).evaluate(),
          isEmpty,
          reason: '首页视频 $postId 不得进入显式播放错误态',
        );
      }
    },
  );
}

Future<bool> _focusVideoCardAndWaitForReady(
  PatrolIntegrationTester $,
  String postId,
) async {
  final card = find.byKey(ValueKey<String>('home-video-player-$postId'));
  final playerReady = find.descendant(
    of: card,
    matching: find.byKey(_readyKey),
  );
  final playerError = find.descendant(
    of: card,
    matching: find.byKey(_errorKey),
  );
  final feedScrollable = find.descendant(
    of: find.byKey(_feedKey),
    matching: find.byType(Scrollable),
  );

  for (var attempt = 0; attempt < 18; attempt++) {
    if (card.evaluate().isNotEmpty) {
      await $.tester.ensureVisible(card.first);
      await $.pump(const Duration(milliseconds: 800));
      for (var readyAttempt = 0; readyAttempt < 12; readyAttempt++) {
        if (playerError.evaluate().isNotEmpty) {
          return false;
        }
        if (playerReady.evaluate().isNotEmpty) {
          return true;
        }
        await $.pump(const Duration(milliseconds: 500));
      }
    }
    if (feedScrollable.evaluate().isEmpty) {
      return false;
    }
    await $.tester.drag(feedScrollable.first, const Offset(0, -540));
    await $.pump(const Duration(milliseconds: 350));
  }
  return false;
}
