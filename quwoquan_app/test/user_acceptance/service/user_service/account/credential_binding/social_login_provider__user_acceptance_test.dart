library;

import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import '../../../../../support/runtime/patrol/patrol_test_support.dart';

import '../../../../../support/runtime/patrol/auth_provider_journey_support.dart';

const _method = String.fromEnvironment('QWQ_PROVIDER_UAT_SOCIAL_METHOD');

void main() {
  patrolTest(
    '真实社交 Provider 完成授权登录',
    tags: const ['user-acceptance', 'user', 'provider', 'social-login'],
    skip: !kRunPatrolAcceptance,
    ($) async {
      final methodLabel = switch (_method.trim().toLowerCase()) {
        'wechat' => FoundationText.loginMethodWechat,
        'qq' => FoundationText.loginMethodQq,
        'alipay' => FoundationText.loginMethodAlipay,
        _ => '',
      };
      expect(
        methodLabel,
        isNotEmpty,
        reason: 'QWQ_PROVIDER_UAT_SOCIAL_METHOD must be wechat, qq, or alipay',
      );
      await launchProviderLogin($);
      await acceptLoginAgreement($);

      if (find.text(methodLabel).evaluate().isEmpty) {
        await $(find.text(FoundationText.loginOtherMethodFallback)).tap();
        await $(
          find.text(methodLabel),
        ).waitUntilVisible(timeout: const Duration(seconds: 15));
      }
      await $(find.text(methodLabel)).tap();
      await waitForProviderLoginSuccess($);
    },
  );
}
