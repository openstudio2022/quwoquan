// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-participant-roster/spec.md#gwt-012
/// 受管 Gamma Gathering 的 production App/Remote 名额提醒 Patrol 入口。
///
/// 该 runner 只证明真实页面读取、typed Watch command、同页 Remote 重新读取与失败
/// fail-closed；当前不登记 readiness_case，因为公开详情尚未返回本人
/// AvailabilityWatch 的 active/version owner readback，同 candidate Android+iPhone
/// ResultBundle 也仍需环境执行。
library;

import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/l10n/copy/gathering_text_constants.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/presentation/gathering_detail_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/user_api_contract_harness.dart';
import '../../../../../support/runtime/patrol/patrol_test_support.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _apiBaseUrl = String.fromEnvironment('API_CONTRACT_BASE_URL');
const _appRuntimeEnv = String.fromEnvironment('APP_RUNTIME_ENV');
const _gatewayBaseUrl = String.fromEnvironment('CLOUD_GATEWAY_BASE_URL');
const _patrolSessionMode = String.fromEnvironment('QWQ_PATROL_SESSION_MODE');
const _gatheringId = String.fromEnvironment(
  'QWQ_GATHERING_PROVIDER_GATHERING_ID',
);
const _expectedTitle = String.fromEnvironment(
  'QWQ_GATHERING_PROVIDER_EXPECTED_TITLE',
);
const _targetConfirmed = bool.fromEnvironment(
  'QWQ_GATHERING_PROVIDER_TARGET_ACK',
);
const _disposableActorConfirmed = bool.fromEnvironment(
  'QWQ_GATHERING_PROVIDER_DISPOSABLE_ACTOR_ACK',
);

void main() {
  patrolTest(
    'gathering_detail_reads_and_watches_managed_full_gathering',
    tags: const ['user-acceptance', 'circle', 'gamma'],
    skip: !kRunPatrolAcceptance,
    config: const PatrolTesterConfig(
      visibleTimeout: Duration(seconds: 30),
      printLogs: true,
    ),
    ($) async {
      _validateRuntimeInputs();
      final suffix = DateTime.now().toUtc().microsecondsSinceEpoch.toString();
      UserApiContractHarness? harness;
      try {
        harness = await UserApiContractHarness.create();
        final session = await harness.loginDisposableAccount(
          'gathering-watch-uat-$suffix',
        );
        final personaId = session.activePersona?.personaId.trim() ?? '';
        if (personaId.isEmpty) {
          throw StateError('Gathering UAT requires an active persona');
        }
        installPatrolAcceptanceSessionForRunner(
          accessToken: session.accessToken,
          refreshToken: session.refreshToken,
          ownerId: session.ownerId,
          personaId: personaId,
        );
        await launchPatrolAppOnce($);

        await _openManagedGathering($);
        final action = find.byKey(GatheringDetailPage.primaryActionKey);
        expect(
          find.descendant(
            of: action,
            matching: find.text(GatheringText.detailWatchAvailabilityAction),
          ),
          findsOneWidget,
        );
        await $(action).tap();
        await _waitForCommandAndRemoteReadback($, action);

        await patrolGoTo($, AppRoutePaths.home);
        await _openManagedGathering($);
        _expectNoGatheringFailure();
      } finally {
        if (harness != null) {
          try {
            await harness.accountLifecycle.closeAccount(
              CloseAccountCommand(
                clientRequestId: 'gathering-watch-uat-cleanup-$suffix',
              ),
            );
          } finally {
            await harness.close();
          }
        }
      }
    },
  );
}

Future<void> _openManagedGathering(PatrolIntegrationTester $) async {
  await patrolGoTo($, AppRoutePaths.gatheringDetail(id: _gatheringId));
  await $(
    find.byType(GatheringDetailPage),
  ).waitUntilVisible(timeout: const Duration(seconds: 30));
  await $(
    find.text(_expectedTitle),
  ).waitUntilVisible(timeout: const Duration(seconds: 30));
  await $(
    find.byKey(GatheringDetailPage.primaryActionKey),
  ).waitUntilVisible(timeout: const Duration(seconds: 30));
  _expectNoGatheringFailure();
}

Future<void> _waitForCommandAndRemoteReadback(
  PatrolIntegrationTester $,
  Finder action,
) async {
  final deadline = DateTime.now().add(const Duration(seconds: 30));
  while (DateTime.now().isBefore(deadline)) {
    _expectNoGatheringFailure();
    final actions = action.evaluate();
    if (actions.isNotEmpty &&
        find.byKey(GatheringDetailPage.loadingKey).evaluate().isEmpty &&
        $.tester.widget<CupertinoButton>(action).onPressed != null) {
      expect(find.text(_expectedTitle), findsWidgets);
      return;
    }
    await $.pump(const Duration(milliseconds: 250));
  }
  fail('Gathering watch command did not reach a Remote readback terminal');
}

void _expectNoGatheringFailure() {
  expect(
    find.byType(AppPageErrorState),
    findsNothing,
    reason: 'Gathering Remote load failure must block UAT',
  );
  expect(
    find.byType(AppSectionErrorCard),
    findsNothing,
    reason: 'Gathering watch failure must not masquerade as success',
  );
}

void _validateRuntimeInputs() {
  if (_apiContractEnv != 'gamma' || _appRuntimeEnv != _apiContractEnv) {
    throw StateError(
      'Gathering UAT requires matching gamma APP_RUNTIME_ENV and '
      'API_CONTRACT_ENV',
    );
  }
  if (_patrolSessionMode.isNotEmpty) {
    throw StateError('Gathering UAT installs its own disposable session');
  }
  final apiGateway = Uri.tryParse(_apiBaseUrl);
  final appGateway = Uri.tryParse(_gatewayBaseUrl);
  if (!_isAbsoluteHttps(apiGateway) || !_isAbsoluteHttps(appGateway)) {
    throw StateError('Gathering UAT requires absolute HTTPS gateways');
  }
  if (_normalizedGateway(apiGateway!) != _normalizedGateway(appGateway!)) {
    throw StateError('Gathering UAT requires one App/API gateway');
  }
  if (!_targetConfirmed ||
      _gatheringId.trim().isEmpty ||
      _expectedTitle.trim().isEmpty) {
    throw StateError('Gathering UAT requires an acknowledged managed target');
  }
  if (!_disposableActorConfirmed) {
    throw StateError(
      'Gathering UAT requires disposable actor cleanup acknowledgement',
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
