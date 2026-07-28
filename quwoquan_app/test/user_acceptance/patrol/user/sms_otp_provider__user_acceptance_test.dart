library;

import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/testing/patrol_test_support.dart';
import 'package:quwoquan_app/ui/user/pages/login_page.dart';

import 'auth_provider_journey_support.dart';

const _phone = String.fromEnvironment('QWQ_PROVIDER_UAT_SMS_PHONE');
const _otp = String.fromEnvironment('QWQ_PROVIDER_UAT_SMS_OTP');

void main() {
  patrolTest(
    '真实短信验证码完成登录',
    tags: const ['t4', 'user', 'provider', 'sms'],
    skip: !kRunPatrolT4,
    ($) async {
      expect(_phone.trim(), isNotEmpty);
      expect(_otp.trim(), isNotEmpty);
      await launchProviderLogin($);

      if (find.byType(PhoneNumberField).evaluate().isEmpty) {
        await $(find.text(FoundationText.loginOtherMethodFallback)).tap();
        await $(
          find.text(FoundationText.loginMethodPhone),
        ).waitUntilVisible(timeout: const Duration(seconds: 15));
        await $(find.text(FoundationText.loginMethodPhone)).tap();
      }

      final phoneField = find.descendant(
        of: find.byType(PhoneNumberField),
        matching: find.byType(CupertinoTextField),
      );
      await $(phoneField).enterText(_phone.trim());
      await acceptLoginAgreement($);
      await $(find.text(FoundationText.loginSendOtp)).tap();

      await $(
        find.byType(OtpCodeBoxes),
      ).waitUntilVisible(timeout: const Duration(seconds: 30));
      final otpField = find.descendant(
        of: find.byType(OtpCodeBoxes),
        matching: find.byType(CupertinoTextField),
      );
      await $(otpField).enterText(_otp.trim());
      await $(find.text(FoundationText.loginPhoneSubmit)).tap();
      await waitForProviderLoginSuccess($);
    },
  );
}
