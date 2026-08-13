// readiness_case: homepage_claim_request_app_uat
// spec_ref: specs/feature-tree/shared-homepage-network/homepage-claim-maintain-and-offline/homepage-claim-request-and-review/spec.md#gwt-002
/// Patrol UAT：disposable persona 经 production App 提交认领，页面内部完成
/// typed receipt + pending readback 后才退出；随后以重复 pending failure 验证
/// 表单保留、显式重试与唯一权威记录。
///
/// 尚无同 candidate Android+iPhone ResultBundle，因此不登记 readiness_case。
library;

import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage_claim_request/presentation/homepage_claim_page.dart';

import '../../../../../support/runtime/api_contract/entity_api_contract_harness.dart';
import '../../../../../support/runtime/patrol/patrol_test_support.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _apiBaseUrl = String.fromEnvironment('API_CONTRACT_BASE_URL');
const _appRuntimeEnv = String.fromEnvironment('APP_RUNTIME_ENV');
const _gatewayBaseUrl = String.fromEnvironment('CLOUD_GATEWAY_BASE_URL');
const _patrolSessionMode = String.fromEnvironment('QWQ_PATROL_SESSION_MODE');
const _homepageId = String.fromEnvironment('QWQ_ENTITY_HOMEPAGE_ID');
const _disposableActorConfirmed = bool.fromEnvironment(
  'QWQ_ENTITY_HOMEPAGE_DISPOSABLE_ACTOR_ACK',
);

void main() {
  patrolTest(
    'homepage_claim_remote_submit_readback_duplicate_failure_and_retry',
    tags: const ['user-acceptance', 'gamma'],
    skip: !kRunPatrolAcceptance,
    config: const PatrolTesterConfig(
      visibleTimeout: Duration(seconds: 20),
      printLogs: true,
    ),
    ($) async {
      _validateRuntimeInputs();
      final harness = await EntityApiContractHarness.create();
      try {
        final detail = await harness.query.getHomepageDetail(_homepageId);
        if (detail.homepageId != _homepageId ||
            detail.status != 'published' ||
            detail.claimStatus == 'claimed') {
          throw StateError(
            'Entity Claim UAT target must be the exact published, unclaimed homepage',
          );
        }
        final personaId = harness.session.activePersona?.personaId.trim() ?? '';
        if (personaId.isEmpty) {
          throw StateError('Entity Claim UAT requires an active persona');
        }
        installPatrolAcceptanceSessionForRunner(
          accessToken: harness.session.accessToken,
          refreshToken: harness.session.refreshToken,
          ownerId: harness.session.ownerId,
          personaId: personaId,
        );
        await launchPatrolAppOnce($);

        await _openClaimPage($);
        await $(find.text(ObjectHomepageText.homepageClaimSubmit)).tap();
        await $(
          find.text(ObjectHomepageText.homepageClaimPhoneRequired),
        ).waitUntilVisible();

        const phone = '13800000000';
        await $(find.byType(CupertinoTextField).first).enterText(phone);
        await $(find.text(ObjectHomepageText.homepageClaimSubmit)).tap();
        await _waitUntilAbsent($, find.byType(HomepageClaimPage));

        final created = await harness.claimRequestReader
            .getMyPendingClaimRequest(homepageId: _homepageId);
        expect(created.homepageId, _homepageId);
        expect(created.requesterPersonaId, personaId);
        expect(created.status.wireName, 'pending_review');

        await _openClaimPage($);
        await $(find.byType(CupertinoTextField).first).enterText(phone);
        await $(find.text(ObjectHomepageText.homepageClaimSubmit)).tap();
        await $(find.byType(AppFormErrorCard)).waitUntilVisible();
        expect(
          $.tester
              .widget<CupertinoTextField>(find.byType(CupertinoTextField).first)
              .controller
              ?.text,
          phone,
          reason: 'duplicate pending failure must preserve valid form input',
        );
        final afterFailure = await harness.claimRequestReader
            .getMyPendingClaimRequest(homepageId: _homepageId);
        expect(afterFailure.claimRequestId, created.claimRequestId);

        final card = $.tester.widget<AppFormErrorCard>(
          find.byType(AppFormErrorCard),
        );
        final retry = card.semantic.primaryAction;
        if (retry == null) {
          throw StateError(
            'Claim failure must expose a canonical retry action',
          );
        }
        await $(find.text(retry.label)).tap();
        await $(find.byType(AppFormErrorCard)).waitUntilVisible();
        final afterRetry = await harness.claimRequestReader
            .getMyPendingClaimRequest(homepageId: _homepageId);
        expect(afterRetry.claimRequestId, created.claimRequestId);
      } finally {
        await harness.close();
      }
    },
  );
}

void _validateRuntimeInputs() {
  if (_apiContractEnv != 'gamma' || _appRuntimeEnv != _apiContractEnv) {
    throw StateError(
      'Entity Claim UAT requires matching gamma APP_RUNTIME_ENV and API_CONTRACT_ENV',
    );
  }
  if (_patrolSessionMode.isNotEmpty) {
    throw StateError('Entity Claim UAT installs its own disposable session');
  }
  if (_homepageId.trim().isEmpty) {
    throw StateError('Entity Claim UAT requires QWQ_ENTITY_HOMEPAGE_ID');
  }
  final apiGateway = Uri.tryParse(_apiBaseUrl);
  final appGateway = Uri.tryParse(_gatewayBaseUrl);
  if (!_isAbsoluteHttps(apiGateway) || !_isAbsoluteHttps(appGateway)) {
    throw StateError(
      'Entity Claim UAT requires absolute HTTPS App and API gateways',
    );
  }
  if (_normalizedGateway(apiGateway!) != _normalizedGateway(appGateway!)) {
    throw StateError(
      'Entity Claim UAT requires App and API to use one gateway',
    );
  }
  if (!_disposableActorConfirmed) {
    throw StateError(
      'Set QWQ_ENTITY_HOMEPAGE_DISPOSABLE_ACTOR_ACK=true only for a disposable actor',
    );
  }
}

Future<void> _openClaimPage(PatrolIntegrationTester $) async {
  await patrolGoTo($, AppRoutePaths.homepageClaim(id: _homepageId));
  await $(find.byType(HomepageClaimPage)).waitUntilVisible();
  await $(find.byType(CupertinoTextField).first).waitUntilVisible();
  expect(find.byType(AppPageErrorState), findsNothing);
}

Future<void> _waitUntilAbsent(PatrolIntegrationTester $, Finder finder) async {
  final deadline = DateTime.now().add(const Duration(seconds: 20));
  while (DateTime.now().isBefore(deadline)) {
    if (finder.evaluate().isEmpty) return;
    await $.pump(const Duration(milliseconds: 250));
  }
  fail('Entity Claim page did not reach its Remote terminal state');
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
