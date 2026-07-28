library;

import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/testing/patrol_test_support.dart';

import 'auth_provider_journey_support.dart';

void main() {
  patrolTest(
    '真实运营商一键登录完成授权',
    tags: const ['t4', 'user', 'provider', 'one-tap-login'],
    skip: !kRunPatrolT4,
    ($) async {
      await launchProviderLogin($);
      await $(
        find.text(FoundationText.loginOneTapPrimary),
      ).waitUntilVisible(timeout: const Duration(seconds: 30));
      await acceptLoginAgreement($);
      await $(find.text(FoundationText.loginOneTapPrimary)).tap();
      await waitForProviderLoginSuccess($);
    },
  );
}
