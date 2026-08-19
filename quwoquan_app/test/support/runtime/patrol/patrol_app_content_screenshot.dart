/// app-content UAT 的页面截图就绪标记：由宿主 stackctl 在标记出现时抓取一帧。
///
/// 标记语义与 `quwoquan_ops/cli/smoke/environment_patrol_smoke` 的
/// `QWQ_APP_CONTENT_PAGE_SCREENSHOT_READY` 消费端一一对应：每次运行只允许出现一次，
/// 且必须携带与目标用例一致的 environment/suite/route/terminalKey。
library;

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';

const String _screenshotReadyMarkerPrefix =
    'QWQ_APP_CONTENT_PAGE_SCREENSHOT_READY ';

/// 宿主观察到标记后才开始抓屏，故这一帧必须在标记之后继续保持可见。
const Duration _hostCaptureWindow = Duration(seconds: 12);

/// 在终态页面上发出一次截图就绪标记，并把该帧保持到宿主抓取完成。
Future<void> emitPatrolAppContentPageScreenshotReady(
  PatrolIntegrationTester $, {
  required String environment,
  required String suite,
  required String route,
  required String terminalKey,
  required Finder terminalFinder,
}) async {
  expect(
    terminalFinder.evaluate(),
    isNotEmpty,
    reason: 'screenshot marker requires the terminal page to be mounted',
  );
  expect(
    terminalKey.trim(),
    isNotEmpty,
    reason: 'screenshot marker requires the terminal key it claims',
  );
  expect(
    route.trim(),
    isNotEmpty,
    reason: 'screenshot marker requires the route it claims',
  );
  await $.pump(const Duration(milliseconds: 600));
  // ignore: avoid_print
  print(
    '$_screenshotReadyMarkerPrefix'
    '${jsonEncode(<String, String>{'environment': environment, 'suite': suite, 'route': route, 'terminalKey': terminalKey})}',
  );
  await $.pump(_hostCaptureWindow);
  expect(
    terminalFinder.evaluate(),
    isNotEmpty,
    reason: 'terminal page must stay mounted while the host captures the frame',
  );
}
