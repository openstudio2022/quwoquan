// spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#gwt-002
library;

import 'dart:convert';
import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import '../../../../../support/runtime/patrol/patrol_test_support.dart';
import 'package:quwoquan_app/service/user_service/account/account_session/presentation/login_page.dart';

import '../../../../../support/runtime/patrol/auth_provider_journey_support.dart';

const _phone = String.fromEnvironment('QWQ_PROVIDER_UAT_SMS_PHONE');
const _otp = String.fromEnvironment('QWQ_PROVIDER_UAT_SMS_OTP');
const _otpBrokerUrl = String.fromEnvironment('QWQ_PROVIDER_UAT_OTP_BROKER_URL');
const _otpBrokerToken = String.fromEnvironment(
  'QWQ_PROVIDER_UAT_OTP_BROKER_TOKEN',
);
const _otpBrokerCaBase64 = String.fromEnvironment(
  'QWQ_PROVIDER_UAT_OTP_BROKER_CA_B64',
);

Uri _validatedOtpBrokerUri(String rawUrl) {
  final uri = Uri.tryParse(rawUrl);
  final isLoopbackHost = uri?.host == '127.0.0.1' || uri?.host == 'localhost';
  if (uri == null ||
      uri.scheme != 'https' ||
      !uri.hasAuthority ||
      !uri.hasPort ||
      !isLoopbackHost ||
      uri.userInfo.isNotEmpty ||
      uri.path != '/v1/otp' ||
      uri.hasQuery ||
      uri.hasFragment) {
    throw StateError(
      'local-capture OTP UAT requires the protected HTTPS loopback broker',
    );
  }
  return uri;
}

Future<String> _resolveOneTimeOtp() async {
  final brokerUrl = _otpBrokerUrl.trim();
  final brokerToken = _otpBrokerToken.trim();
  final brokerCaBase64 = _otpBrokerCaBase64.trim();
  final hasBroker =
      brokerUrl.isNotEmpty ||
      brokerToken.isNotEmpty ||
      brokerCaBase64.isNotEmpty;
  if (hasBroker) {
    if (brokerUrl.isEmpty || brokerToken.isEmpty || brokerCaBase64.isEmpty) {
      throw StateError(
        'local-capture OTP UAT requires broker URL, token, and pinned CA',
      );
    }
    if (_otp.trim().isNotEmpty) {
      throw StateError(
        'local-capture OTP UAT must use protected readback, not argv OTP',
      );
    }
    final brokerUri = _validatedOtpBrokerUri(brokerUrl);
    final securityContext = SecurityContext(withTrustedRoots: false)
      ..setTrustedCertificatesBytes(base64Decode(brokerCaBase64));
    final client = HttpClient(context: securityContext);
    try {
      final request = await client.postUrl(brokerUri);
      request.headers.set(
        HttpHeaders.authorizationHeader,
        'Bearer $brokerToken',
      );
      final response = await request.close();
      final body = await utf8.decoder.bind(response).join();
      if (response.statusCode != HttpStatus.ok) {
        throw StateError('protected OTP broker did not return a code');
      }
      final payload = jsonDecode(body);
      final code = payload is Map<String, dynamic>
          ? (payload['code'] as String? ?? '')
          : '';
      if (!RegExp(r'^[0-9]{6}$').hasMatch(code)) {
        throw StateError('protected OTP broker returned an invalid code');
      }
      return code;
    } finally {
      client.close(force: true);
    }
  }
  if (!RegExp(r'^[0-9]{6}$').hasMatch(_otp.trim())) {
    throw StateError(
      'managed-nonprod Provider UAT requires a six-digit OTP or broker',
    );
  }
  return _otp.trim();
}

void main() {
  patrolTest(
    'Provider 短信验证码完成登录',
    tags: const ['user-acceptance', 'user', 'provider', 'sms'],
    skip: !kRunPatrolAcceptance,
    ($) async {
      expect(_phone.trim(), isNotEmpty);
      expect(
        _otp.trim().isNotEmpty ||
            (_otpBrokerUrl.trim().isNotEmpty &&
                _otpBrokerToken.trim().isNotEmpty &&
                _otpBrokerCaBase64.trim().isNotEmpty),
        isTrue,
      );
      await launchProviderLogin($);
      await $.pumpAndSettle();

      if (find.byType(LoginPhoneField).evaluate().isEmpty) {
        final otherMethod = find.text(
          FoundationText.loginOtherMethodFallback,
        );
        if (otherMethod.evaluate().isNotEmpty) {
          await $(otherMethod).tap();
          await $(
            find.text(FoundationText.loginMethodPhone),
          ).waitUntilVisible(timeout: const Duration(seconds: 15));
          await $(find.text(FoundationText.loginMethodPhone)).tap();
        }
      }
      await $(
        find.byType(LoginPhoneField),
      ).waitUntilVisible(timeout: const Duration(seconds: 15));

      final phoneField = find.descendant(
        of: find.byType(LoginPhoneField),
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
      final otp = await _resolveOneTimeOtp();
      await $(otpField).enterText(otp);
      await waitForProviderLoginSuccess($);
    },
  );
}
