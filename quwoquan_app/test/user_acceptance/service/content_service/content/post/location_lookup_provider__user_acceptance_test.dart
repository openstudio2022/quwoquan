library;

import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import '../../../../../support/runtime/patrol/patrol_test_support.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/publish_location_selector_page.dart';

const _query = String.fromEnvironment('QWQ_PROVIDER_UAT_LOCATION_QUERY');
const _expected = String.fromEnvironment(
  'QWQ_PROVIDER_UAT_LOCATION_EXPECTED_TEXT',
);

void main() {
  patrolTest(
    '真实地点 Provider 搜索结果进入发布选点页',
    tags: const ['user-acceptance', 'content', 'provider', 'location'],
    skip: !kRunPatrolAcceptance,
    ($) async {
      expect(_query.trim(), isNotEmpty);
      expect(_expected.trim(), isNotEmpty);
      await launchPatrolAppOnce($);

      final navigatorElement = find.byType(Navigator).evaluate().first;
      final container = ProviderScope.containerOf(navigatorElement);
      final coordinator = container.read(createLocationCoordinatorProvider);
      unawaited(
        Navigator.of(navigatorElement).push<void>(
          CupertinoPageRoute<void>(
            builder: (_) =>
                PublishLocationSearchPage(locationCoordinator: coordinator),
          ),
        ),
      );
      await $.pump();

      await $(
        find.byType(PublishLocationSearchPage),
      ).waitUntilVisible(timeout: const Duration(seconds: 30));
      await $(find.byType(CupertinoSearchTextField)).enterText(_query.trim());
      await $(
        find.textContaining(_expected.trim()),
      ).waitUntilVisible(timeout: const Duration(seconds: 30));
    },
  );
}
