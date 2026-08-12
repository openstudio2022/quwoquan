// spec_ref: specs/feature-tree/shared-homepage-network/homepage-claim-maintain-and-offline/homepage-offline-report-and-history-retention/spec.md#gwt-002
/// Patrol UAT：disposable persona 经 production App 提交状态上报，页面内部完成
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
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage_status_report/presentation/homepage_status_report_page.dart';

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
    'homepage_status_report_remote_submit_readback_duplicate_failure_and_retry',
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
        if (detail.homepageId != _homepageId || detail.status != 'published') {
          throw StateError(
            'Entity StatusReport UAT target must be the exact published homepage',
          );
        }
        final personaId = harness.session.activePersona?.personaId.trim() ?? '';
        if (personaId.isEmpty) {
          throw StateError(
            'Entity StatusReport UAT requires an active persona',
          );
        }
        installPatrolAcceptanceSessionForRunner(
          accessToken: harness.session.accessToken,
          refreshToken: harness.session.refreshToken,
          ownerId: harness.session.ownerId,
          personaId: personaId,
        );
        await launchPatrolAppOnce($);

        await _openStatusReportPage($);
        await $(find.text(ObjectHomepageText.homepageStatusReportSubmit)).tap();
        await $(
          find.text(ObjectHomepageText.homepageStatusReportReasonRequired),
        ).waitUntilVisible();

        await $(
          find.text(ObjectHomepageText.homepageStatusReportReasonIncorrectInfo),
        ).tap();
        const description = 'candidate authoritative readback';
        await $(find.byType(CupertinoTextField)).enterText(description);
        await $(find.text(ObjectHomepageText.homepageStatusReportSubmit)).tap();
        await _waitUntilAbsent($, find.byType(HomepageStatusReportPage));

        final created = await harness.statusReportReader
            .getMyPendingStatusReport(
              homepageId: _homepageId,
              reason: 'incorrect_info',
            );
        expect(created.homepageId, _homepageId);
        expect(created.reporterPersonaId, personaId);
        expect(created.status.wireName, 'pending_review');

        await _openStatusReportPage($);
        await $(
          find.text(ObjectHomepageText.homepageStatusReportReasonIncorrectInfo),
        ).tap();
        await $(find.byType(CupertinoTextField)).enterText(description);
        await $(find.text(ObjectHomepageText.homepageStatusReportSubmit)).tap();
        await $(find.byType(AppFormErrorCard)).waitUntilVisible();
        expect(
          $.tester
              .widget<CupertinoTextField>(find.byType(CupertinoTextField))
              .controller
              ?.text,
          description,
          reason: 'duplicate pending failure must preserve valid form input',
        );
        final afterFailure = await harness.statusReportReader
            .getMyPendingStatusReport(
              homepageId: _homepageId,
              reason: 'incorrect_info',
            );
        expect(afterFailure.reportId, created.reportId);

        final card = $.tester.widget<AppFormErrorCard>(
          find.byType(AppFormErrorCard),
        );
        final retry = card.semantic.primaryAction;
        if (retry == null) {
          throw StateError(
            'StatusReport failure must expose a canonical retry action',
          );
        }
        await $(find.text(retry.label)).tap();
        await $(find.byType(AppFormErrorCard)).waitUntilVisible();
        final afterRetry = await harness.statusReportReader
            .getMyPendingStatusReport(
              homepageId: _homepageId,
              reason: 'incorrect_info',
            );
        expect(afterRetry.reportId, created.reportId);
      } finally {
        await harness.close();
      }
    },
  );
}

void _validateRuntimeInputs() {
  if (_apiContractEnv != 'gamma' || _appRuntimeEnv != _apiContractEnv) {
    throw StateError(
      'Entity StatusReport UAT requires matching gamma APP_RUNTIME_ENV and API_CONTRACT_ENV',
    );
  }
  if (_patrolSessionMode.isNotEmpty) {
    throw StateError(
      'Entity StatusReport UAT installs its own disposable session',
    );
  }
  if (_homepageId.trim().isEmpty) {
    throw StateError('Entity StatusReport UAT requires QWQ_ENTITY_HOMEPAGE_ID');
  }
  final apiGateway = Uri.tryParse(_apiBaseUrl);
  final appGateway = Uri.tryParse(_gatewayBaseUrl);
  if (!_isAbsoluteHttps(apiGateway) || !_isAbsoluteHttps(appGateway)) {
    throw StateError(
      'Entity StatusReport UAT requires absolute HTTPS App and API gateways',
    );
  }
  if (_normalizedGateway(apiGateway!) != _normalizedGateway(appGateway!)) {
    throw StateError(
      'Entity StatusReport UAT requires App and API to use one gateway',
    );
  }
  if (!_disposableActorConfirmed) {
    throw StateError(
      'Set QWQ_ENTITY_HOMEPAGE_DISPOSABLE_ACTOR_ACK=true only for a disposable actor',
    );
  }
}

Future<void> _openStatusReportPage(PatrolIntegrationTester $) async {
  await patrolGoTo($, AppRoutePaths.homepageStatusReport(id: _homepageId));
  await $(find.byType(HomepageStatusReportPage)).waitUntilVisible();
  await $(
    find.text(ObjectHomepageText.homepageStatusReportReasonIncorrectInfo),
  ).waitUntilVisible();
  expect(find.byType(AppPageErrorState), findsNothing);
}

Future<void> _waitUntilAbsent(PatrolIntegrationTester $, Finder finder) async {
  final deadline = DateTime.now().add(const Duration(seconds: 20));
  while (DateTime.now().isBefore(deadline)) {
    if (finder.evaluate().isEmpty) return;
    await $.pump(const Duration(milliseconds: 250));
  }
  fail('Entity StatusReport page did not reach its Remote terminal state');
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
