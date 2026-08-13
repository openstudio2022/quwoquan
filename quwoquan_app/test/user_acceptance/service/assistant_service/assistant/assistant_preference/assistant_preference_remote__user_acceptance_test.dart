// readiness_case: assistant_preference_management_app_uat
// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/session-preference-memory-control/spec.md#gwt-003
/// Disposable owner 在 production App 中设置、遗忘并恢复长期回答偏好，每次动作后
/// 都通过离页重入触发 production Remote 权威读取。
///
/// Gamma 尚无受治理的 preference selective-failure orchestration，因此本 runner
/// 不登记 readiness_case，也不冒充 GWT-003 的失败恢复或双真机证据。
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/l10n/copy/assistant_text_constants.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_preference/presentation/assistant_management_page.dart';

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
  'QWQ_ASSISTANT_PREFERENCE_DISPOSABLE_ACTOR_ACK',
);

void main() {
  patrolTest(
    'assistant_preference_remote_set_revoke_restore_and_reopen',
    tags: const ['user-acceptance', 'assistant', 'gamma'],
    skip: !kRunPatrolAcceptance,
    config: const PatrolTesterConfig(
      visibleTimeout: Duration(seconds: 20),
      printLogs: true,
    ),
    ($) async {
      _validateRuntimeInputs();
      final harness = await AssistantApiContractHarness.create(
        'preference-uat',
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

        await _openManagement($);
        await $(find.text(AssistantText.assistantPreferenceConcise).first).tap();
        await _waitForPreferenceAction(
          $,
          AssistantText.assistantPreferenceForget,
        );

        await _reopenManagement($);
        expect(
          find.text(AssistantText.assistantPreferenceForget),
          findsOneWidget,
          reason: 'SetAssistantPreference 必须由 production Remote 重入读回',
        );
        await $(find.text(AssistantText.assistantPreferenceForget)).tap();
        await _waitForPreferenceAction(
          $,
          AssistantText.assistantPreferenceUndo,
        );

        await _reopenManagement($);
        expect(
          find.text(AssistantText.assistantPreferenceUndo),
          findsOneWidget,
          reason: 'RevokeAssistantPreference 必须由 revoked 列表重入读回',
        );
        await $(find.text(AssistantText.assistantPreferenceUndo)).tap();
        await _waitForPreferenceAction(
          $,
          AssistantText.assistantPreferenceForget,
        );

        await _reopenManagement($);
        expect(
          find.text(AssistantText.assistantPreferenceForget),
          findsOneWidget,
          reason: 'RestoreAssistantPreference 必须由 active 列表重入读回',
        );
        expect(
          find.text(AssistantText.assistantPreferenceUndo),
          findsNothing,
        );
      } finally {
        await harness.close();
      }
    },
  );
}

void _validateRuntimeInputs() {
  if (_apiContractEnv != 'gamma' || _appRuntimeEnv != _apiContractEnv) {
    throw StateError(
      'AssistantPreference UAT requires matching gamma APP_RUNTIME_ENV and '
      'API_CONTRACT_ENV',
    );
  }
  if (_patrolSessionMode.isNotEmpty) {
    throw StateError('AssistantPreference UAT installs its own owner session');
  }
  final apiGateway = Uri.tryParse(_apiBaseUrl);
  final appGateway = Uri.tryParse(_gatewayBaseUrl);
  if (!_isAbsoluteHttps(apiGateway) || !_isAbsoluteHttps(appGateway)) {
    throw StateError(
      'AssistantPreference UAT requires absolute HTTPS API and App gateways',
    );
  }
  if (_normalizedGateway(apiGateway!) != _normalizedGateway(appGateway!)) {
    throw StateError(
      'AssistantPreference UAT requires App and API to use the same gateway',
    );
  }
  if (!_disposableActorConfirmed) {
    throw StateError(
      'Set QWQ_ASSISTANT_PREFERENCE_DISPOSABLE_ACTOR_ACK=true only when '
      'public CloseAccount cleanup is permitted',
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

Future<void> _openManagement(PatrolIntegrationTester $) async {
  await patrolGoTo($, AppRoutePaths.assistantManagement);
  await $(
    find.byType(AssistantManagementPage),
  ).waitUntilVisible(timeout: const Duration(seconds: 20));
  await $(
    find.text(AssistantText.assistantPreferenceDefaultsTitle),
  ).waitUntilVisible(timeout: const Duration(seconds: 20));
  _expectNoFailure();
}

Future<void> _reopenManagement(PatrolIntegrationTester $) async {
  await patrolGoTo($, AppRoutePaths.home);
  await _openManagement($);
}

Future<void> _waitForPreferenceAction(
  PatrolIntegrationTester $,
  String actionLabel,
) async {
  final deadline = DateTime.now().add(const Duration(seconds: 20));
  while (DateTime.now().isBefore(deadline)) {
    _expectNoFailure();
    if (find.text(actionLabel).evaluate().isNotEmpty) {
      return;
    }
    await $.pump(const Duration(milliseconds: 250));
  }
  fail('AssistantPreference did not converge to action: $actionLabel');
}

void _expectNoFailure() {
  expect(
    find.byType(AppSectionErrorCard),
    findsNothing,
    reason: 'AssistantPreference Remote failure cannot masquerade as success',
  );
}
