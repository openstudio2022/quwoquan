/// user_acceptance Patrol：当前不可变发布物首页视频卡的原生自动播放验收。
library;

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import '../../../support/runtime/patrol/patrol_test_support.dart';

const _releaseId = String.fromEnvironment('DATA_RELEASE_ID');
const _homeVideoPostId = String.fromEnvironment(
  'VIDEO_PLAYBACK_CANARY_WORK_ID',
);
const _feedKey = ValueKey<String>('home-feed-recommend');
const _readyKey = ValueKey<String>('video-player-ready');
const _nativeFirstFrameKey = ValueKey<String>(
  'video-player-native-first-frame',
);
const _errorKey = ValueKey<String>('video-player-error');

void main() {
  patrolTest(
    'environment_home_video_playback',
    tags: ['user-acceptance', 'environment-smoke', 'video-playback'],
    skip: !kRunPatrolAcceptance,
    config: PatrolTesterConfig(
      visibleTimeout: const Duration(seconds: 12),
      printLogs: true,
    ),
    ($) async {
      _expectReleaseEnvelope();
      await launchPatrolAppOnce($);
      await patrolGoTo($, AppRoutePaths.home);

      final renderedFirstFrame = await _focusVideoCardAndWaitForFirstFrame(
        $,
        _homeVideoPostId,
      );
      expect(
        renderedFirstFrame,
        isTrue,
        reason:
            '发布物 $_releaseId 的首页视频 $_homeVideoPostId '
            '应在稳定可见后 6 秒内呈现原生首帧，'
            '不得以 controller ready 冒充可用',
      );
      expect(
        find.byKey(_errorKey).evaluate(),
        isEmpty,
        reason: '首页视频 $_homeVideoPostId 不得进入显式播放错误态',
      );
    },
  );
}

void _expectReleaseEnvelope() {
  final required = <String, String>{
    'DATA_RELEASE_ID': _releaseId,
    'VIDEO_PLAYBACK_CANARY_WORK_ID': _homeVideoPostId,
  };
  for (final entry in required.entries) {
    expect(
      entry.value.trim(),
      isNotEmpty,
      reason:
          '${entry.key} must bind home video playback to one immutable release',
    );
  }
}

Future<bool> _focusVideoCardAndWaitForFirstFrame(
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
  final nativeFirstFrame = find.descendant(
    of: card,
    matching: find.byKey(_nativeFirstFrameKey),
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
        if (playerReady.evaluate().isNotEmpty &&
            nativeFirstFrame.evaluate().isNotEmpty) {
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
