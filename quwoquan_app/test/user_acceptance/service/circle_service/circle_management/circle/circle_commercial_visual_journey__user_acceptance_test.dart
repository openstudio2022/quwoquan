// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-001
// spec_ref: specs/feature-tree/circle-community/circle-management-and-stats/kpi-reporting/spec.md#gwt-001
/// 圈子主页商用化真机视觉与主旅程前置。
///
/// 该用例只允许使用 production Remote composition；运行方必须提供与当前 candidate
/// 绑定、当前 actor 可管理的真实 Circle。设备截图由统一的 Patrol 环境 runner 在
/// 用例前后采集，避免与 PatrolBinding 竞争 Flutter test binding。
library;

import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import '../../../../../support/runtime/patrol/patrol_test_support.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/presentation/circle_detail_page.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/presentation/circle_edit_settings_page.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/presentation/circle_stats_page.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/presentation/home_circles_hub_page.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _runtimeEnv = String.fromEnvironment('APP_RUNTIME_ENV');
const _patrolSessionMode = String.fromEnvironment('QWQ_PATROL_SESSION_MODE');
const _gatewayBaseUrl = String.fromEnvironment('CLOUD_GATEWAY_BASE_URL');
const _circleId = String.fromEnvironment('QWQ_CIRCLE_VISUAL_CIRCLE_ID');
const _circleName = String.fromEnvironment('QWQ_CIRCLE_VISUAL_CIRCLE_NAME');
const _managerActorConfirmed = bool.fromEnvironment(
  'QWQ_CIRCLE_VISUAL_MANAGER_ACTOR_ACK',
);
const _physicalDeviceConfirmed = bool.fromEnvironment(
  'QWQ_CIRCLE_VISUAL_PHYSICAL_DEVICE_ACK',
);
const _moreActionKey = ValueKey<String>('object-chrome-more');

void main() {
  patrolTest(
    'circle_commercial_remote_visual_journey',
    tags: ['user-acceptance', 'circle', 'gamma', 'visual'],
    skip: !kRunPatrolAcceptance,
    config: PatrolTesterConfig(visibleTimeout: const Duration(seconds: 20)),
    ($) async {
      _validateRuntimeInputs();
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
        find.text(_circleName.trim()),
        reason: '圈子详情必须显示 candidate 绑定的真实 Remote 圈名',
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
        find.text(CommunityText.editCircle),
        reason: 'Gamma 验收会话必须具有圈子管理权限',
      );
      await $(find.text(CommunityText.editCircle)).tap();
      await _expectVisible(
        $,
        find.byType(CircleEditSettingsPage),
        reason: '圈子编辑页必须从真实管理旅程进入',
      );
    },
  );
}

void _validateRuntimeInputs() {
  if (_runtimeEnv != 'gamma' || _apiContractEnv != _runtimeEnv) {
    throw StateError(
      'Circle visual UAT requires matching gamma APP_RUNTIME_ENV and '
      'API_CONTRACT_ENV',
    );
  }
  if (_patrolSessionMode.isNotEmpty) {
    throw StateError(
      'Circle visual UAT requires an injected authenticated manager actor; '
      'anonymous sessions are not evidence',
    );
  }
  final gateway = Uri.tryParse(_gatewayBaseUrl);
  if (gateway == null || gateway.scheme != 'https' || gateway.host.isEmpty) {
    throw StateError('Circle visual UAT requires an absolute HTTPS gateway');
  }
  if (_circleId.trim().isEmpty || _circleName.trim().isEmpty) {
    throw StateError(
      'Circle visual UAT requires a candidate-bound circle id and name',
    );
  }
  if (!_managerActorConfirmed) {
    throw StateError(
      'Circle visual UAT requires explicit confirmation that the injected '
      'actor manages the candidate-bound Circle',
    );
  }
  if (!_physicalDeviceConfirmed ||
      kIsWeb ||
      (defaultTargetPlatform != TargetPlatform.android &&
          defaultTargetPlatform != TargetPlatform.iOS)) {
    throw StateError(
      'Circle visual UAT requires an acknowledged Android or iPhone '
      'physical device',
    );
  }
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
