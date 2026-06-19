/// T4 Patrol E2E: 环境页面基本可用性 smoke。
///
/// 固定覆盖部署后最容易断的五个入口：首页、我的、他人主页、记录列表、视频流。
library;

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/testing/patrol_test_support.dart';

const _otherUserId = 'fixture_user_friend';
const _videoWorkId = 'fixture_video_001';

const _feedCardProbeKeys = <ValueKey<String>>[
  ValueKey<String>('home-feed-card-0'),
  ValueKey<String>('dual-discovery-card-0'),
];
const _profileProbeKeys = <ValueKey<String>>[
  ValueKey<String>('profile-header-avatar'),
  ValueKey<String>('profile-shell-summary-card'),
];
const _videoProbeKeys = <ValueKey<String>>[
  ValueKey<String>('works-video-stage-$_videoWorkId-0'),
  ValueKey<String>('works-video-$_videoWorkId-0'),
  ValueKey<String>('home-video-player-$_videoWorkId'),
];

void main() {
  patrolTest(
    'environment_basic_viability_smoke',
    tags: ['t4', 'environment-smoke'],
    skip: !kRunPatrolT4,
    config: PatrolTesterConfig(visibleTimeout: const Duration(seconds: 12)),
    ($) async {
      await launchPatrolAppOnce($);

      await _expectHomeFeed($);
      await _goTo($, AppRoutePaths.profile);
      await _expectProfileShell($, label: 'my profile');
      await _goTo($, AppRoutePaths.userProfile(username: _otherUserId));
      await _expectProfileShell($, label: 'other profile');
      await _goTo($, AppRoutePaths.myFootprint());
      await _expectFootprintListShell($);
      await _goTo(
        $,
        AppRoutePaths.workBrowser(
          workId: _videoWorkId,
          source: 'environmentSmoke',
        ),
      );
      await _expectVideoFlow($);
    },
  );
}

Future<void> _expectHomeFeed(PatrolIntegrationTester $) async {
  final visible = await _waitForAnyKey($, _feedCardProbeKeys);
  expect(
    visible,
    isTrue,
    reason: 'environment smoke requires at least one home feed card',
  );
}

Future<void> _expectProfileShell(
  PatrolIntegrationTester $, {
  required String label,
}) async {
  final visible = await _waitForAnyKey($, _profileProbeKeys);
  expect(visible, isTrue, reason: '$label shell should render');
}

Future<void> _expectFootprintListShell(PatrolIntegrationTester $) async {
  final visible = await _waitForAnyFinder($, <Finder>[
    find.text(UITextConstants.myFootprintTitle),
    find.text(UITextConstants.myFootprintPrivacyHint),
    find.text(UITextConstants.myFootprintEmpty),
  ]);
  expect(visible, isTrue, reason: 'footprint list shell should render');
}

Future<void> _expectVideoFlow(PatrolIntegrationTester $) async {
  final visible = await _waitForAnyKey(
    $,
    _videoProbeKeys,
    timeout: const Duration(seconds: 60),
  );
  expect(visible, isTrue, reason: 'video flow should render first video stage');
}

Future<void> _goTo(PatrolIntegrationTester $, String location) async {
  final router = _findGoRouter($);
  router.go(location);
  await $.pump();
  await $.pump(const Duration(milliseconds: 300));
  await $.pump(const Duration(seconds: 1));
}

GoRouter _findGoRouter(PatrolIntegrationTester $) {
  for (final element in find.byType(Navigator).evaluate()) {
    try {
      return GoRouter.of(element);
    } catch (_) {
      continue;
    }
  }
  throw StateError('GoRouter is not available in the current Patrol tree');
}

Future<bool> _waitForAnyKey(
  PatrolIntegrationTester $,
  Iterable<Key> keys, {
  Duration timeout = const Duration(seconds: 40),
}) {
  return _waitForAnyFinder($, keys.map(find.byKey), timeout: timeout);
}

Future<bool> _waitForAnyFinder(
  PatrolIntegrationTester $,
  Iterable<Finder> finders, {
  Duration timeout = const Duration(seconds: 40),
}) async {
  final deadline = DateTime.now().add(timeout);
  while (DateTime.now().isBefore(deadline)) {
    for (final finder in finders) {
      if (finder.evaluate().isNotEmpty) {
        return true;
      }
    }
    await $.pump(const Duration(milliseconds: 500));
  }
  return false;
}
