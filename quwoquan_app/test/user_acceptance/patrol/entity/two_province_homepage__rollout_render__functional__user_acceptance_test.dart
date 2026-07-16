import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/core/testing/patrol_test_support.dart';
import '../../../support/gamma_homepage_uat_cases.dart';

const _encodedUatCases = String.fromEnvironment(
  'QWQ_TWO_PROVINCE_UAT_CASES_B64',
);

void main() {
  patrolTest(
    'two_province_homepage_rollout_render',
    tags: ['t4', 'entity-homepage', 'two-province-rollout'],
    skip: !kRunPatrolT4,
    config: PatrolTesterConfig(visibleTimeout: const Duration(seconds: 20)),
    ($) async {
      final homepages = parseGammaHomepageUatCases(_encodedUatCases);
      await launchPatrolAppOnce($);

      for (final homepage in homepages) {
        await patrolGoTo(
          $,
          AppRoutePaths.homepageDetail(id: homepage.homepageId),
        );
        expect(
          await _waitFor($, find.byKey(TestKeys.homepageDetailPage)),
          isTrue,
          reason: '${homepage.title} detail must load from Gamma',
        );
        expect(find.byKey(TestKeys.homepageDetailPage), findsOneWidget);

        await patrolGoTo(
          $,
          AppRoutePaths.homepageIntroduction(id: homepage.homepageId),
        );
        expect(
          await _waitFor($, find.text('认识${homepage.title}')),
          isTrue,
          reason: '${homepage.title} introduction must load from Gamma',
        );
        expect(find.text('认识${homepage.title}'), findsOneWidget);
        expect(
          await _scrollUntilVisible(
            $,
            find.text(UITextConstants.objectIntroSourceTitle),
          ),
          isTrue,
          reason: '${homepage.title} source disclosure must be reachable',
        );
      }
    },
  );
}

Future<bool> _waitFor(PatrolIntegrationTester $, Finder finder) async {
  await $.pump();
  final deadline = DateTime.now().add(const Duration(seconds: 45));
  while (DateTime.now().isBefore(deadline)) {
    if (finder.evaluate().isNotEmpty) {
      return true;
    }
    await $.pump(const Duration(milliseconds: 500));
  }
  return false;
}

Future<bool> _scrollUntilVisible(
  PatrolIntegrationTester $,
  Finder finder,
) async {
  for (var attempt = 0; attempt < 16; attempt += 1) {
    if (finder.evaluate().isNotEmpty) {
      return true;
    }
    final list = find.byType(ListView);
    if (list.evaluate().isEmpty) {
      return false;
    }
    await $.tester.drag(list.first, const Offset(0, -600));
    await $.pump(const Duration(milliseconds: 300));
  }
  return finder.evaluate().isNotEmpty;
}
