// spec_ref: specs/feature-tree/user-identity-profile-relationship/onboarding-and-identity-entry/four-environment-commercial-login-maturity/spec.md#gwt-012
// spec_ref: specs/feature-tree/user-identity-profile-relationship/onboarding-and-identity-entry/four-environment-commercial-login-maturity/spec.md#gwt-012.t4
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/platform/otp_autofill_gateway.dart';

void main() {
  test(
    'Retriever accepts one six-digit code bound to the current request ref',
    () {
      final parsed = parseSmsRetrieverOtp(
        '<#> 趣我圈验证码 482731\nrequestRef: otp_req_current\nFA+9qCX9VSu',
        expectedRequestRef: 'otp_req_current',
      );
      expect(parsed?.code, '482731');
      expect(parsed?.requestRef, 'otp_req_current');
    },
  );

  test(
    'Retriever rejects old refs, malformed codes, and ambiguous messages',
    () {
      expect(
        parseSmsRetrieverOtp(
          '验证码 482731\nrequestRef: otp_req_old',
          expectedRequestRef: 'otp_req_current',
        ),
        isNull,
      );
      expect(
        parseSmsRetrieverOtp(
          '验证码 48273\nrequestRef: otp_req_current',
          expectedRequestRef: 'otp_req_current',
        ),
        isNull,
      );
      expect(
        parseSmsRetrieverOtp(
          '验证码 482731 593842\nrequestRef: otp_req_current',
          expectedRequestRef: 'otp_req_current',
        ),
        isNull,
      );
    },
  );
}
