import 'dart:convert';
import 'dart:math';

import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show
        AlipayAuthorizationGrant,
        CreateAlipayAuthorizationRequestCommand,
        OneTapLoginHint,
        OtpClientPlatform,
        OtpChallengeIssueResult,
        ResolveOneTapLoginHintCommand,
        SendOtpCommand;

enum OtpDeliveryReadinessAvailability { ready, temporarilyUnavailable }

class OtpDeliveryReadinessSnapshot {
  const OtpDeliveryReadinessSnapshot({
    required this.availability,
    required this.retryAfterSeconds,
  });

  final OtpDeliveryReadinessAvailability availability;
  final int retryAfterSeconds;

  bool get isReady => availability == OtpDeliveryReadinessAvailability.ready;
}

/// 生成不含手机号/设备信息的 128-bit opaque SendOtp 幂等键。
String newOtpIdempotencyKey() {
  final random = Random.secure();
  final bytes = List<int>.generate(16, (_) => random.nextInt(256));
  return base64UrlEncode(bytes).replaceAll('=', '');
}

OtpClientPlatform otpClientPlatformForRuntime(String platform) {
  return switch (platform.trim().toLowerCase()) {
    'ios' => OtpClientPlatform.ios,
    'android' => OtpClientPlatform.android,
    'web' => OtpClientPlatform.web,
    _ => OtpClientPlatform.web,
  };
}

abstract interface class AuthenticationChallengeWriter {
  Future<OtpDeliveryReadinessSnapshot> getOtpDeliveryReadiness();

  Future<OtpChallengeIssueResult> sendOtp(
    SendOtpCommand command, {
    required String idempotencyKey,
  });

  Future<AlipayAuthorizationGrant> createAlipayAuthorizationRequest(
    CreateAlipayAuthorizationRequestCommand command,
  );

  Future<OneTapLoginHint> resolveOneTapLoginHint(
    ResolveOneTapLoginHintCommand command,
  );
}
