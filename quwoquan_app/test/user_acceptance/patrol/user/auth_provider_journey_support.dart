library;

import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/core/testing/patrol_test_support.dart';
import 'package:quwoquan_app/ui/user/pages/login_page.dart';

Future<void> launchProviderLogin(PatrolIntegrationTester $) async {
  await launchPatrolAppOnce($);
  await patrolGoTo($, AppRoutePaths.login(redirect: AppRoutePaths.home));
  await $(
    find.byType(LoginPage),
  ).waitUntilVisible(timeout: const Duration(seconds: 30));
}

Future<void> acceptLoginAgreement(PatrolIntegrationTester $) async {
  final agreementIcon = find.descendant(
    of: find.byType(LoginPage),
    matching: find.byIcon(CupertinoIcons.circle),
  );
  await $(agreementIcon.first).tap();
  await $.pump(const Duration(milliseconds: 300));
}

Future<void> waitForProviderLoginSuccess(PatrolIntegrationTester $) async {
  final deadline = DateTime.now().add(const Duration(seconds: 90));
  while (DateTime.now().isBefore(deadline)) {
    await $.pump(const Duration(milliseconds: 500));
    if (find.byType(LoginPage).evaluate().isEmpty) {
      return;
    }
  }
  fail('Provider login did not leave LoginPage before timeout');
}
