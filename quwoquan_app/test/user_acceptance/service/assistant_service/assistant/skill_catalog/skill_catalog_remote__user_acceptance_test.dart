// readiness_case: skill_catalog_disclosure_app_uat
// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/skill-progressive-disclosure-routing/spec.md#gwt-003
/// 已认证 disposable owner 经 production Remote 打开 Skill Center，并读取
/// official travel_companion 的账号隔离目录状态。
///
/// 匿名拒绝与授权存储 unavailable 仍缺受治理的环境故障编排，因此本 runner 不登记
/// readiness_case，也不冒充完整 GWT-003 或商用结果。
library;

import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/skill_catalog/presentation/assistant_skill_center_page.dart';

import '../../../../../support/runtime/api_contract/assistant_api_contract_harness.dart';
import '../../../../../support/runtime/patrol/patrol_test_support.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _apiBaseUrl = String.fromEnvironment('API_CONTRACT_BASE_URL');
const _appRuntimeEnv = String.fromEnvironment('APP_RUNTIME_ENV');
const _patrolSessionMode = String.fromEnvironment('QWQ_PATROL_SESSION_MODE');
const _gatewayBaseUrl = String.fromEnvironment('CLOUD_GATEWAY_BASE_URL');
const _disposableActorConfirmed = bool.fromEnvironment(
  'QWQ_SKILL_CATALOG_DISPOSABLE_ACTOR_ACK',
);
const _travelSkillKey = ValueKey<String>(
  'assistant_skill_detail_travel_companion',
);

void main() {
  patrolTest(
    'skill_catalog_remote_lists_official_skill_for_verified_owner',
    tags: const ['user-acceptance', 'assistant', 'gamma'],
    skip: !kRunPatrolAcceptance,
    config: const PatrolTesterConfig(
      visibleTimeout: Duration(seconds: 20),
      printLogs: true,
    ),
    ($) async {
      _validateRuntimeInputs();
      final harness = await AssistantApiContractHarness.create(
        'skill-catalog-uat',
      );
      try {
        final personaId = harness.session.activePersona?.personaId.trim() ?? '';
        if (personaId.isEmpty) {
          throw StateError('Disposable Assistant owner has no active persona');
        }
        installPatrolAcceptanceSessionForRunner(
          accessToken: harness.session.accessToken,
          refreshToken: harness.session.refreshToken,
          ownerId: harness.session.ownerId,
          personaId: personaId,
        );
        await launchPatrolAppOnce($);

        await _openSkillCenter($);
        await $(
          find.byKey(_travelSkillKey),
        ).waitUntilVisible(timeout: const Duration(seconds: 20));
        _expectCatalogAvailable();

        await patrolGoTo($, AppRoutePaths.home);
        await _openSkillCenter($);
        await $(
          find.byKey(_travelSkillKey),
        ).waitUntilVisible(timeout: const Duration(seconds: 20));
        _expectCatalogAvailable();
      } finally {
        await harness.close();
      }
    },
  );
}

void _validateRuntimeInputs() {
  if (_apiContractEnv != 'gamma' || _appRuntimeEnv != _apiContractEnv) {
    throw StateError(
      'SkillCatalog UAT requires matching gamma APP_RUNTIME_ENV and '
      'API_CONTRACT_ENV',
    );
  }
  if (_patrolSessionMode.isNotEmpty) {
    throw StateError('SkillCatalog UAT installs its own owner session');
  }
  final apiGateway = Uri.tryParse(_apiBaseUrl);
  final appGateway = Uri.tryParse(_gatewayBaseUrl);
  if (!_isAbsoluteHttps(apiGateway) || !_isAbsoluteHttps(appGateway)) {
    throw StateError(
      'SkillCatalog UAT requires absolute HTTPS API and App gateways',
    );
  }
  if (_normalizedGateway(apiGateway!) != _normalizedGateway(appGateway!)) {
    throw StateError('SkillCatalog UAT requires one App/API gateway');
  }
  if (!_disposableActorConfirmed) {
    throw StateError(
      'Set QWQ_SKILL_CATALOG_DISPOSABLE_ACTOR_ACK=true only when public '
      'CloseAccount cleanup is permitted',
    );
  }
}

bool _isAbsoluteHttps(Uri? value) =>
    value != null &&
    value.isAbsolute &&
    value.scheme == 'https' &&
    value.host.isNotEmpty;

String _normalizedGateway(Uri value) {
  final path = value.path.replaceFirst(RegExp(r'/+$'), '');
  return value.replace(path: path, query: null, fragment: null).toString();
}

Future<void> _openSkillCenter(PatrolIntegrationTester $) async {
  await patrolGoTo($, AppRoutePaths.assistantSkills);
  await $(
    find.byType(AssistantSkillCenterPage),
  ).waitUntilVisible(timeout: const Duration(seconds: 20));
}

void _expectCatalogAvailable() {
  expect(
    find.byType(AppSectionErrorCard),
    findsNothing,
    reason: 'SkillCatalog unavailable cannot masquerade as an empty catalog',
  );
  expect(find.byKey(_travelSkillKey), findsOneWidget);
}
