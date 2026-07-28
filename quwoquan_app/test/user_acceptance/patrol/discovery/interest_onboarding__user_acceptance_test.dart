/// Gamma-local remote UAT for the first-run interest flow.
///
/// The test starts the production Remote composition, signs in through the
/// local user-service boundary, reads taxonomy leaves from tag-service, and
/// waits for Content's confirmed submission before the route returns home.
// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/interest-onboarding-prior/spec.md#gwt-001
library;

import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/testing/patrol_test_support.dart';

const _pageKey = ValueKey<String>('interest-onboarding-page');
const _submitKey = ValueKey<String>('interest-onboarding-submit');
const _homeSearchKey = ValueKey<String>('home-search-chrome');

void main() {
  patrolTest(
    'interest onboarding selects a remote taxonomy leaf and returns after confirmation',
    tags: const <String>['t4', 'gamma', 'content', 'onboarding'],
    skip: !kRunPatrolT4,
    config: PatrolTesterConfig(visibleTimeout: const Duration(seconds: 15)),
    ($) async {
      await launchPatrolAppOnce($);
      await patrolGoTo($, AppRoutePaths.interestOnboarding);

      final pageVisible = await _waitFor(
        $,
        find.byKey(_pageKey),
        timeout: const Duration(seconds: 30),
      );
      expect(pageVisible, isTrue, reason: '兴趣页必须从真实 Gamma taxonomy 加载');
      expect(
        find.text(ProfileText.interestOnboardingTitle),
        findsOneWidget,
      );

      final leafOption = find.byWidgetPredicate((widget) {
        if (widget is! CupertinoButton) return false;
        final key = widget.key;
        return key is ValueKey<String> &&
            key.value.startsWith('interest-onboarding-option-');
      });
      final optionVisible = await _waitFor(
        $,
        leafOption,
        timeout: const Duration(seconds: 30),
      );
      expect(optionVisible, isTrue, reason: '页面只能展示可提交的 taxonomy 叶节点');
      await $.tester.tap(leafOption.first);
      await $.pump(const Duration(milliseconds: 300));

      await $.tester.tap(find.byKey(_submitKey));
      final returnedHome = await _waitFor(
        $,
        find.byKey(_homeSearchKey),
        timeout: const Duration(seconds: 30),
      );
      expect(returnedHome, isTrue, reason: '服务端确认兴趣事件后必须失效首屏并回到首页');
    },
  );
}

Future<bool> _waitFor(
  PatrolIntegrationTester $,
  Finder finder, {
  required Duration timeout,
}) async {
  final deadline = DateTime.now().add(timeout);
  while (DateTime.now().isBefore(deadline)) {
    if (finder.evaluate().isNotEmpty) return true;
    await $.pump(const Duration(milliseconds: 500));
  }
  return false;
}
