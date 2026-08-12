// spec_ref: specs/feature-tree/user-identity-profile-relationship/onboarding-and-identity-entry/four-environment-commercial-login-maturity/spec.md#gwt-011.t1
// readiness_case: pending-otp-attempt-secure-recovery-local
import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/user_service/account/authentication_challenge/adapters/secure_pending_otp_attempt_store.dart';
import 'package:quwoquan_app/service/user_service/account/authentication_challenge/application/public/authentication_challenge_writer.dart';
import 'package:quwoquan_app/service/user_service/account/authentication_challenge/application/public/pending_otp_attempt_store.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    FlutterSecureStorage.setMockInitialValues(<String, String>{});
  });

  test('pending OTP attempt round-trips without persisting an OTP', () async {
    const secureStorage = FlutterSecureStorage();
    const store = SecurePendingOtpAttemptStore(storage: secureStorage);
    final now = DateTime.now();
    final attempt = PendingOtpAttempt(
      phone: '18038139016',
      maskedPhone: '180****9016',
      idempotencyKey: 'otp-idempotency-0000000000000001',
      challengeId: 'otp_ch_1',
      requestId: 'otp_req_1',
      deliveryStatus: 'confirming',
      resendDeadlineEpochMs: now
          .add(const Duration(seconds: 60))
          .millisecondsSinceEpoch,
      expiresAtEpochMs: now
          .add(const Duration(minutes: 5))
          .millisecondsSinceEpoch,
    );

    await store.write(attempt);
    final restored = await store.read();
    expect(restored?.idempotencyKey, attempt.idempotencyKey);
    expect(restored?.phone, attempt.phone);
    expect(restored?.deliveryStatus, 'confirming');

    final securePayload = (await secureStorage.readAll()).values.single;
    expect(securePayload, isNot(contains('otpCode')));
    expect(securePayload, isNot(contains('verificationCode')));
    expect(attempt.toJson().keys, isNot(contains('otp')));
  });

  test(
    'expired or malformed pending attempts are removed fail-closed',
    () async {
      const secureStorage = FlutterSecureStorage();
      const store = SecurePendingOtpAttemptStore(storage: secureStorage);
      final expired = PendingOtpAttempt(
        phone: '18038139016',
        maskedPhone: '180****9016',
        idempotencyKey: 'otp-idempotency-0000000000000002',
        deliveryStatus: 'queued',
        resendDeadlineEpochMs: DateTime.now().millisecondsSinceEpoch,
        expiresAtEpochMs: DateTime.now()
            .subtract(const Duration(seconds: 1))
            .millisecondsSinceEpoch,
      );
      await store.write(expired);
      expect(await store.read(), isNull);
      expect(await secureStorage.readAll(), isEmpty);

      FlutterSecureStorage.setMockInitialValues(<String, String>{
        'auth.pending_otp_attempt.v1': jsonEncode(<String, Object?>{
          'phone': '18038139016',
          'idempotencyKey': 'too-short',
        }),
      });
      expect(await store.read(), isNull);
      expect(await secureStorage.readAll(), isEmpty);
    },
  );

  test('SendOtp idempotency key is opaque random 128-bit material', () {
    final keys = List<String>.generate(64, (_) => newOtpIdempotencyKey());
    expect(keys.toSet(), hasLength(keys.length));
    for (final key in keys) {
      expect(base64Url.decode(base64Url.normalize(key)), hasLength(16));
      expect(key, isNot(contains('18038139016')));
    }
  });
}
