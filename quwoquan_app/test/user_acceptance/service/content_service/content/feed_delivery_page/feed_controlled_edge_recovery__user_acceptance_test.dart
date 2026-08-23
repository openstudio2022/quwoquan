// readiness_case: feed_delivery_page_edge_recovery_app_uat
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/error-permission-display-semantics/spec.md#gwt-009
// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
library;

import 'dart:convert';

import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import '../../../../../support/runtime/patrol/patrol_test_support.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';

const _runtimeEnv = String.fromEnvironment(
  'APP_RUNTIME_ENV',
  defaultValue: 'gamma',
);

const _expectedCopies =
    <({String copyKey, String title, String message, String action})>[
      (
        copyKey: 'connectionUnavailable',
        title: SearchText.recoveryConnectionUnavailableTitle,
        message: SearchText.recoveryConnectionUnavailableMessage,
        action: SearchText.reload,
      ),
      (
        copyKey: 'requestTimedOut',
        title: SearchText.recoveryRequestTimedOutTitle,
        message: SearchText.recoveryRequestTimedOutMessage,
        action: SearchText.reload,
      ),
      (
        copyKey: 'serviceUnavailable',
        title: SearchText.recoveryServiceUnavailableTitle,
        message: SearchText.recoveryServiceUnavailableMessage,
        action: SearchText.reload,
      ),
      (
        copyKey: 'guestSessionUnavailable',
        title: SearchText.recoveryGuestSessionUnavailableTitle,
        message: SearchText.recoveryGuestSessionUnavailableMessage,
        action: SearchText.reload,
      ),
    ];

void main() {
  patrolTest(
    'feed_controlled_edge_failure_copy_and_same_install_recovery',
    tags: ['user-acceptance', 'discovery'],
    skip: !kRunPatrolAcceptance,
    config: PatrolTesterConfig(
      visibleTimeout: const Duration(seconds: 20),
      printLogs: true,
    ),
    ($) async {
      assert(
        const {'alpha', 'beta', 'gamma'}.contains(_runtimeEnv),
        'Controlled edge recovery must bind one canonical nonprod runtime.',
      );
      await launchPatrolAppOnce($);

      final errorFinder = find.byType(AppPageErrorState);
      expect(
        await _waitForFinder($, errorFinder),
        isTrue,
        reason:
            'A stopped receipt-bound API Edge must reach a page error terminal.',
      );
      final errorState = $.tester.widget<AppPageErrorState>(errorFinder);
      final matchedCopy = _expectedCopies.where(
        (copy) =>
            copy.title == errorState.semantic.title &&
            copy.message == errorState.semantic.message &&
            copy.action == errorState.semantic.primaryAction?.label,
      );
      expect(
        matchedCopy,
        hasLength(1),
        reason:
            'The visible title, explanation and action must form one canonical recovery group.',
      );
      expect(errorState.semantic.secondaryAction, isNull);

      final primaryButtons = find.descendant(
        of: errorFinder,
        matching: find.byType(CupertinoButton),
      );
      expect(primaryButtons, findsOneWidget);
      expect(
        find.descendant(of: errorFinder, matching: find.byType(Icon)),
        findsNothing,
      );

      final visibleCopy = find
          .descendant(of: errorFinder, matching: find.byType(Text))
          .evaluate()
          .map((element) => (element.widget as Text).data ?? '')
          .join('\n');
      expect(
        visibleCopy.contains(SettingsText.settingsAppOfficialName),
        isFalse,
      );
      for (final technicalToken in const <String>[
        'DNS',
        'TLS',
        'HTTP',
        'requestId',
        'traceId',
        '127.0.0.1',
      ]) {
        expect(visibleCopy.contains(technicalToken), isFalse);
      }

      final copy = matchedCopy.single;
      for (var retry = 0; retry < 5; retry += 1) {
        await $.tester.tap(
          find.descendant(of: errorFinder, matching: find.text(copy.action)),
        );
        await $.pump(const Duration(seconds: 7));
        expect(
          errorFinder,
          findsOneWidget,
          reason:
              'Retry ${retry + 1} while the service is stopped must keep the typed blocking terminal.',
        );
      }
      // ignore: avoid_print
      print(
        'QWQ_APP_CONTENT_EDGE_RESTORE_REQUEST '
        '${jsonEncode(<String, Object>{'environment': _runtimeEnv, 'observed': true, 'copyKey': copy.copyKey, 'blockedRetryCount': 5})}',
      );

      // Host-side stackctl restores the exact receipt-bound containers after it
      // observes the marker. The wait is bounded by the controller's health
      // deadline and does not reinstall or relaunch the App.
      await $.pump(const Duration(seconds: 65));
      await $.tester.tap(
        find.descendant(of: errorFinder, matching: find.text(copy.action)),
      );
      await $.pump();

      expect(
        await _waitForAnyFeedCard($),
        isTrue,
        reason:
            'Retry must recover release-bound content in the same App installation.',
      );
      final recoveredCount = _visibleFeedCardKeys().length;
      expect(recoveredCount, greaterThan(0));
      // ignore: avoid_print
      print(
        'QWQ_APP_CONTENT_FAULT_EVIDENCE '
        '${jsonEncode(<String, Object>{'environment': _runtimeEnv, 'copyKey': copy.copyKey, 'singlePrimaryAction': true, 'forbiddenBrandAbsent': true, 'technicalDetailsAbsent': true, 'blockedRetryCount': 5, 'blockingErrorRetained': true, 'sameInstallRecovery': true, 'recoveredVisibleCardCount': recoveredCount})}',
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

Future<bool> _waitForAnyFeedCard(PatrolIntegrationTester $) async {
  final deadline = DateTime.now().add(const Duration(seconds: 60));
  while (DateTime.now().isBefore(deadline)) {
    if (_visibleFeedCardKeys().isNotEmpty) return true;
    await $.pump(const Duration(milliseconds: 500));
  }
  return _visibleFeedCardKeys().isNotEmpty;
}

Future<bool> _waitForFinder(
  PatrolIntegrationTester $,
  Finder finder, {
  Duration timeout = const Duration(seconds: 60),
}) async {
  final deadline = DateTime.now().add(timeout);
  while (DateTime.now().isBefore(deadline)) {
    if (finder.evaluate().isNotEmpty) return true;
    await $.pump(const Duration(milliseconds: 500));
  }
  return finder.evaluate().isNotEmpty;
}
