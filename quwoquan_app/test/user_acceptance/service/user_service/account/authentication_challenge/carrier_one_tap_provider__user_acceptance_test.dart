// spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#gwt-002
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import '../../../../../support/runtime/patrol/patrol_test_support.dart';

import '../../../../../support/runtime/patrol/auth_provider_journey_support.dart';

void main() {
  patrolTest(
    '真实运营商一键登录完成授权',
    tags: const ['user-acceptance', 'user', 'provider', 'one-tap-login'],
    skip: !kRunPatrolAcceptance,
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
