// spec_ref: specs/feature-tree/user-identity-profile-relationship/onboarding-and-identity-entry/four-environment-commercial-login-maturity/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/onboarding-and-identity-entry/two-state-one-tap-login-commercial-login-entry/spec.md#gwt-003
// readiness_case: authentication_challenge_send_otp_app_local
// readiness_case: authentication_challenge_get_otp_delivery_readiness_app_local
// readiness_case: authentication_challenge_create_alipay_authorization_request_app_local
// readiness_case: authentication_challenge_resolve_one_tap_login_hint_app_local
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/user_service/account/authentication_challenge/adapters/authentication_challenge_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/transport/cloud_operation_routing_recorder.dart';

void main() {
  test(
    'Authentication challenge commands keep exact generated operation ownership',
    () async {
      final executor = CloudOperationRoutingRecorder(
        responseFor: (operation) => switch (operation.canonicalOperationId) {
          AppCloudOperationIds
              .userAuthenticationChallengeGetOtpDeliveryReadiness =>
            <String, Object?>{
              'availability': 'ready',
              'retryAfterSeconds': 0,
            },
          AppCloudOperationIds.userAuthenticationChallengeSendOtp =>
            <String, Object?>{
              'maskedPhone': '138****0000',
              'expiresInSeconds': 300,
              'deliveryStatus': 'queued',
              'retryAfterSeconds': 60,
              'requestId': 'otp-request-1',
              'challengeId': 'otp-challenge-1',
            },
          AppCloudOperationIds
              .userAuthenticationChallengeCreateAlipayAuthorizationRequest =>
            <String, Object?>{
              'authorizationPayload': 'signed-authorization',
              'expiresAt': '2026-08-08T16:00:00Z',
            },
          AppCloudOperationIds
              .userAuthenticationChallengeResolveOneTapLoginHint =>
            <String, Object?>{
              'state': 'ready',
              'maskedPhone': '138****0000',
              'registered': true,
              'expiresInSeconds': 120,
            },
          _ => throw StateError(
            'unexpected operation ${operation.canonicalOperationId}',
          ),
        },
      );
      final writer = RemoteAuthenticationChallengeCommandWriter(
        client: GeneratedCloudOperationClient(executor),
        invocationContext: (clientPageId, {String? idempotencyKey}) =>
            CloudOperationInvocationContext(
              surfaceId: 'login',
              clientPageId: clientPageId,
              idempotencyKey: idempotencyKey,
              actor: const CloudOperationActorContext(accountId: 'account-1'),
            ),
      );

      final readiness = await writer.getOtpDeliveryReadiness();
      final otp = await writer.sendOtp(
        SendOtpCommand(
          phone: '13800000000',
          platform: OtpClientPlatform.ios,
          sourceOperation: 'bind_phone',
          bindingTicket: 'binding-ticket-1',
        ),
        idempotencyKey: 'otp-idempotency-key-000000000001',
      );
      final alipay = await writer.createAlipayAuthorizationRequest(
        CreateAlipayAuthorizationRequestCommand(platform: 'ios'),
      );
      final oneTap = await writer.resolveOneTapLoginHint(
        ResolveOneTapLoginHintCommand(
          vendor: 'aliyun',
          carrierToken: 'carrier-token',
          deviceId: 'device-1',
          platform: 'ios',
        ),
      );

      expect(readiness.isReady, isTrue);
      expect(otp.deliveryStatus, OtpDeliveryStatus.queued);
      expect(alipay.authorizationPayload, 'signed-authorization');
      expect(oneTap.state, 'ready');
      expect(
        executor.calls.map((call) => call.operation.canonicalOperationId),
        <String>[
          AppCloudOperationIds
              .userAuthenticationChallengeGetOtpDeliveryReadiness,
          AppCloudOperationIds.userAuthenticationChallengeSendOtp,
          AppCloudOperationIds
              .userAuthenticationChallengeCreateAlipayAuthorizationRequest,
          AppCloudOperationIds
              .userAuthenticationChallengeResolveOneTapLoginHint,
        ],
      );
      expect(
        executor.calls[1].payload.body,
        containsPair('phone', '13800000000'),
      );
      expect(
        executor.calls[1].context.idempotencyKey,
        'otp-idempotency-key-000000000001',
      );
      expect(executor.calls[2].payload.body, <String, Object?>{
        'platform': 'ios',
      });
      expect(executor.calls[3].payload.body, containsPair('vendor', 'aliyun'));
    },
  );
}
