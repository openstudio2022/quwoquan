// readiness_case: contact_discovery_phone_contacts_app_uat
// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/follow-relationship/spec.md#gwt-002
/// 物理通讯录 → production Remote discovery → typed Follow → capability
/// readback 的标准 Patrol source runner。
///
/// 运行前，受管设备必须预置一个属于真实 Gamma Provider 账号的联系人；测试只接收
/// 非敏感本机显示名，不接收手机号、hash 或 bearer。当前不登记 readiness_case：同
/// candidate Android+iPhone、权限拒绝与 Remote 故障恢复 ResultBundle 尚未齐备。
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/user_service/relationship/contact_discovery_record/presentation/phone_contacts_page.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/presentation/contact_candidate_row.dart';
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
const _expectedContactName = String.fromEnvironment(
  'QWQ_CONTACT_DISCOVERY_EXPECTED_DISPLAY_NAME',
);
const _physicalContactConfirmed = bool.fromEnvironment(
  'QWQ_CONTACT_DISCOVERY_PHYSICAL_CONTACT_ACK',
);
const _disposableActorConfirmed = bool.fromEnvironment(
  'QWQ_CONTACT_DISCOVERY_DISPOSABLE_ACTOR_ACK',
);

void main() {
  patrolTest(
    'phone_contacts_discovers_and_follows_a_real_provider_identity',
    tags: const ['user-acceptance', 'user', 'gamma'],
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
          'phone-contacts-$suffix',
        );
        final personaId = session.activePersona?.personaId.trim() ?? '';
        if (personaId.isEmpty) {
          throw StateError('PhoneContacts UAT requires an active persona');
        }
        installPatrolAcceptanceSessionForRunner(
          accessToken: session.accessToken,
          refreshToken: session.refreshToken,
          ownerId: session.ownerId,
          personaId: personaId,
        );
        await launchPatrolAppOnce($);

        await _openAndLoadPhysicalContacts($);
        final row = _expectedContactRow();
        final addAction = find.descendant(
          of: row,
          matching: find.text(ContactText.addContact),
        );
        await $(
          addAction,
        ).waitUntilVisible(timeout: const Duration(seconds: 45));
        await $(addAction).tap();
        await _waitForAuthoritativeFollowReadback($, row);

        await patrolGoTo($, AppRoutePaths.home);
        await _openAndLoadPhysicalContacts($);
        await _waitForAuthoritativeFollowReadback($, _expectedContactRow());
      } finally {
        if (harness != null) {
          try {
            await harness.accountLifecycle.closeAccount(
              CloseAccountCommand(
                clientRequestId: 'phone-contacts-cleanup-$suffix',
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

Future<void> _openAndLoadPhysicalContacts(PatrolIntegrationTester $) async {
  await patrolGoTo($, AppRoutePaths.addContactPhone);
  await $(
    find.byType(PhoneContactsPage),
  ).waitUntilVisible(timeout: const Duration(seconds: 30));
  await $(find.text(ContactText.phoneContactsPermissionCta)).tap();
  await _grantContactsPermission($);
  await $(
    find.text(_expectedContactName),
  ).waitUntilVisible(timeout: const Duration(seconds: 45));
  expect(_expectedContactRow(), findsOneWidget);
}

Future<void> _grantContactsPermission(PatrolIntegrationTester $) async {
  for (var attempt = 0; attempt < 3; attempt += 1) {
    if (!await $.platform.mobile.isPermissionDialogVisible(
      timeout: const Duration(seconds: 3),
    )) {
      return;
    }
    await $.platform.mobile.grantPermissionWhenInUse();
    await $.pump(const Duration(milliseconds: 500));
  }
  if (await $.platform.mobile.isPermissionDialogVisible(
    timeout: const Duration(seconds: 1),
  )) {
    throw StateError('contacts permission did not reach a terminal choice');
  }
}

Future<void> _waitForAuthoritativeFollowReadback(
  PatrolIntegrationTester $,
  Finder row,
) async {
  final added = find.descendant(
    of: row,
    matching: find.text(ContactText.contactAlreadyAdded),
  );
  await $(added).waitUntilVisible(timeout: const Duration(seconds: 30));
  expect(
    find.descendant(of: row, matching: find.text(ContactText.addContact)),
    findsNothing,
    reason: 'Follow UI must change only after production Remote readback',
  );
}

Finder _expectedContactRow() => find.ancestor(
  of: find.text(_expectedContactName),
  matching: find.byType(ContactCandidateRow),
);

void _validateRuntimeInputs() {
  if (_apiContractEnv != 'gamma' || _appRuntimeEnv != _apiContractEnv) {
    throw StateError(
      'PhoneContacts UAT requires matching gamma APP_RUNTIME_ENV and '
      'API_CONTRACT_ENV',
    );
  }
  if (_patrolSessionMode.isNotEmpty) {
    throw StateError('PhoneContacts UAT installs its own disposable session');
  }
  final apiGateway = Uri.tryParse(_apiBaseUrl);
  final appGateway = Uri.tryParse(_gatewayBaseUrl);
  if (!_isAbsoluteHttps(apiGateway) || !_isAbsoluteHttps(appGateway)) {
    throw StateError('PhoneContacts UAT requires absolute HTTPS gateways');
  }
  if (_normalizedGateway(apiGateway!) != _normalizedGateway(appGateway!)) {
    throw StateError('PhoneContacts UAT requires one App/API gateway');
  }
  if (!_physicalContactConfirmed || _expectedContactName.trim().isEmpty) {
    throw StateError(
      'PhoneContacts UAT requires an acknowledged managed physical contact',
    );
  }
  if (!_disposableActorConfirmed) {
    throw StateError(
      'PhoneContacts UAT requires disposable actor cleanup acknowledgement',
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
