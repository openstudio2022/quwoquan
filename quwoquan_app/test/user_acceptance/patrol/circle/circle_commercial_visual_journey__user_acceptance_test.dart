/// 圈子主页商用化真机视觉与主旅程证据。
///
/// 该用例只允许使用 production Remote composition；运行方必须提供可管理
/// `fixture_circle_photo` 的真实 Gamma 会话。设备截图由统一的 Patrol 环境 runner
/// 在用例前后采集，避免与 PatrolBinding 竞争 Flutter test binding。
library;

import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/testing/patrol_test_support.dart';
import 'package:quwoquan_app/ui/circle/pages/circle_detail_page.dart';
import 'package:quwoquan_app/ui/circle/pages/circle_edit_settings_page.dart';
import 'package:quwoquan_app/ui/circle/pages/circle_stats_page.dart';
import 'package:quwoquan_app/ui/circle/pages/home_circles_hub_page.dart';

const _circleId = 'fixture_circle_photo';
const _runtimeEnv = String.fromEnvironment('APP_RUNTIME_ENV');
const _moreActionKey = ValueKey<String>('object-chrome-more');

void main() {
  patrolTest(
    'circle_commercial_remote_visual_journey',
    tags: ['t4', 'circle', 'gamma', 'visual'],
    skip: !kRunPatrolT4,
    config: PatrolTesterConfig(visibleTimeout: const Duration(seconds: 20)),
    ($) async {
      expect(
        _runtimeEnv,
        'gamma',
        reason: '圈子商用视觉证据必须来自 Gamma Remote composition',
      );
      await launchPatrolAppOnce($);

      await patrolGoTo($, AppRoutePaths.circles);
      await _expectVisible(
        $,
        find.byType(CirclesHubPage),
        reason: '圈子 hub 必须可达',
      );

      await patrolGoTo($, AppRoutePaths.circleDetail(id: _circleId));
      await _expectVisible(
        $,
        find.byType(CircleDetailPage),
        reason: '圈子详情必须渲染真实 Gamma 数据',
      );
      await _expectVisible(
        $,
        find.text('契约摄影社'),
        reason: '圈子详情必须显示 Gamma fixture 圈名',
      );

      await patrolGoTo(
        $,
        AppRoutePaths.circleStats(id: _circleId, type: 'members'),
      );
      await _expectVisible(
        $,
        find.byType(CircleStatsPage),
        reason: '圈子统计页必须可达',
      );

      await patrolGoTo($, AppRoutePaths.circleDetail(id: _circleId));
      await _expectVisible(
        $,
        find.byKey(_moreActionKey),
        reason: '圈子详情必须提供对象操作入口',
      );
      await $(find.byKey(_moreActionKey)).tap();
      await _expectVisible(
        $,
        find.text(UITextConstants.editCircle),
        reason: 'Gamma 验收会话必须具有圈子管理权限',
      );
      await $(find.text(UITextConstants.editCircle)).tap();
      await _expectVisible(
        $,
        find.byType(CircleEditSettingsPage),
        reason: '圈子编辑页必须从真实管理旅程进入',
      );
    },
  );
}

Future<void> _expectVisible(
  PatrolIntegrationTester $,
  Finder finder, {
  required String reason,
  Duration timeout = const Duration(seconds: 30),
}) async {
  final deadline = DateTime.now().add(timeout);
  while (DateTime.now().isBefore(deadline)) {
    if (finder.evaluate().isNotEmpty) {
      return;
    }
    await $.pump(const Duration(milliseconds: 500));
  }
  expect(finder, findsWidgets, reason: reason);
}
