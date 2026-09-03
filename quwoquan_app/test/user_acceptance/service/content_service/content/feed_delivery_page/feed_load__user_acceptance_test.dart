/// user_acceptance Patrol: 发现页 Feed 加载旅程
///
/// 对应 e2e.yaml 场景：discovery_feed_load_and_render [test_type: ui_journey]
///
/// 守护：发现页全链路（app → gamma → content-service）可渲染内容卡片
/// 只测 flutter_test 无法替代的行为：真实网络请求、真实设备渲染
///
/// 注：Patrol test host 的临时 wrapper 启动 production app.main()；本 test
///     直接与已运行的 App 交互，不需要 pumpWidget。
///
/// 执行方式（本地，需连接真机或模拟器）：
///   patrol test test/user_acceptance/service/content_service/content/feed_delivery_page/feed_load__user_acceptance_test.dart \
///     --dart-define=APP_RUNTIME_ENV=gamma \
///     --dart-define=API_CONTRACT_ENV=gamma \
///     --dart-define=RUN_PATROL_ACCEPTANCE=true \
///     --dart-define=TEST_AUTH_TOKEN=YOUR_TOKEN
///
/// CI：由 .github/workflows/e2e.yaml 在 pre-release tag 时触发。
library;

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:flutter/widgets.dart';
import 'package:go_router/go_router.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart'
    show appImageLoadErrorKey, appImageLoadSuccessKey;
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';

import '../../../../../support/runtime/patrol/patrol_app_content_screenshot.dart';
import '../../../../../support/runtime/patrol/patrol_test_support.dart';

const _feedCardProbeKeys = <ValueKey<String>>[
  ValueKey<String>('home-feed-card-0'),
];

// dart-define 注入
const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _runtimeEnv = String.fromEnvironment(
  'APP_RUNTIME_ENV',
  defaultValue: 'gamma',
);

void main() {
  patrolTest(
    'discovery_feed_load_and_render',
    tags: ['user-acceptance', 'discovery'],
    skip: !kRunPatrolAcceptance,
    config: PatrolTesterConfig(
      visibleTimeout: const Duration(seconds: 10),
      printLogs: true,
    ),
    ($) async {
      await launchPatrolAppOnce($);

      assert(
        _apiContractEnv == _runtimeEnv &&
            const {'alpha', 'beta', 'gamma'}.contains(_runtimeEnv),
        'Patrol user_acceptance tests must bind API_CONTRACT_ENV to the selected nonprod runtime',
      );

      // ── 等待首页真实 feed 卡片及该卡片自己的媒体解码终态 ────────────
      final visibleFeedCardKey = await _waitForVisibleFeedCard($);
      expect(
        visibleFeedCardKey,
        isNotNull,
        reason:
            'At least one $_runtimeEnv feed card must be visible after load',
      );
      final terminalKey = visibleFeedCardKey!.value;
      final visibleFeedCard = find.byKey(visibleFeedCardKey).first;
      final feedCardImageSuccess = find.descendant(
        of: visibleFeedCard,
        matching: find.byKey(appImageLoadSuccessKey),
      );
      expect(
        await _waitForFinder($, feedCardImageSuccess),
        isTrue,
        reason:
            'the visible home feed card itself must decode media; an avatar elsewhere '
            'cannot satisfy feed media readback',
      );
      expect(
        find.descendant(
          of: visibleFeedCard,
          matching: find.byKey(appImageLoadErrorKey),
        ),
        findsNothing,
        reason:
            'the visible home feed card must not render a media error state',
      );
      final terminalRoute = GoRouterState.of($.tester.element(visibleFeedCard))
          .uri
          .path;
      expect(
        terminalRoute,
        AppRoutePaths.home,
        reason:
            'feed evidence must remain bound to the current home feed route',
      );
      final visibleCardKeys = _visibleFeedCardKeys();
      expect(visibleCardKeys, contains(terminalKey));
      // The host-side Patrol runner captures the Dart test process stdout.
      // PatrolTester.log is not forwarded by iOS XCTest, so it cannot carry
      // release-bound acceptance evidence across the device boundary.
      // ignore: avoid_print
      print(
        'QWQ_FEED_CONTENT_EVIDENCE '
        '${jsonEncode(<String, Object>{'environment': _runtimeEnv, 'visibleCardCount': visibleCardKeys.length, 'visibleCardKeys': visibleCardKeys, 'terminalKey': terminalKey, 'route': terminalRoute, 'mediaLoadStatus': 'decoded'})}',
      );
      await emitPatrolAppContentPageScreenshotReady(
        $,
        environment: _runtimeEnv,
        suite: 'discovery-feed-load-and-render',
        route: terminalRoute,
        terminalKey: terminalKey,
        terminalFinder: visibleFeedCard,
      );
    },
  );
}

List<String> _visibleFeedCardKeys() {
  final visible = <String>[];
  for (var index = 0; index < 20; index += 1) {
    for (final prefix in const <String>['home-feed-card-']) {
      final key = '$prefix$index';
      if (find.byKey(ValueKey<String>(key)).evaluate().isNotEmpty) {
        visible.add(key);
      }
    }
  }
  return visible;
}

Future<ValueKey<String>?> _waitForVisibleFeedCard(
  PatrolIntegrationTester $,
) async {
  final deadline = DateTime.now().add(const Duration(seconds: 40));
  while (DateTime.now().isBefore(deadline)) {
    for (final key in _feedCardProbeKeys) {
      if ($(key).visible) {
        return key;
      }
    }
    await $.pump(const Duration(milliseconds: 500));
  }
  return null;
}

Future<bool> _waitForFinder(PatrolIntegrationTester $, Finder finder) async {
  final deadline = DateTime.now().add(const Duration(seconds: 45));
  while (DateTime.now().isBefore(deadline)) {
    await $.pump();
    if (finder.evaluate().isNotEmpty) return true;
    await $.pump(const Duration(milliseconds: 250));
  }
  return false;
}
