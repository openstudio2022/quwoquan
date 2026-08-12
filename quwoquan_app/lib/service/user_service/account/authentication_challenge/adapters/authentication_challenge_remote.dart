import 'package:quwoquan_app/runtime/transport/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/service/user_service/account/authentication_challenge/application/public/authentication_challenge_writer.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef AuthenticationChallengeInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId, {
      String? idempotencyKey,
    });

/// AuthenticationChallenge 的 production generated-client adapter。
final class RemoteAuthenticationChallengeCommandWriter
    implements AuthenticationChallengeWriter {
  const RemoteAuthenticationChallengeCommandWriter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final AuthenticationChallengeInvocationContextFactory invocationContext;

  @override
  Future<OtpDeliveryReadinessSnapshot> getOtpDeliveryReadiness() async {
    final result = await client
        .userAuthenticationChallengeGetOtpDeliveryReadiness(
          const OtpDeliveryReadinessQuery(),
          context: invocationContext(
            UserRequestPageIds.getOtpDeliveryReadiness,
          ),
        );
    return OtpDeliveryReadinessSnapshot(
      availability: result.availability == OtpDeliveryAvailability.ready
          ? OtpDeliveryReadinessAvailability.ready
          : OtpDeliveryReadinessAvailability.temporarilyUnavailable,
      retryAfterSeconds: result.retryAfterSeconds,
    );
  }

  @override
  Future<OtpChallengeIssueResult> sendOtp(
    SendOtpCommand command, {
    required String idempotencyKey,
  }) => client.userAuthenticationChallengeSendOtp(
    command,
    context: invocationContext(
      UserRequestPageIds.sendOtp,
      idempotencyKey: idempotencyKey,
    ),
  );

  @override
  Future<AlipayAuthorizationGrant> createAlipayAuthorizationRequest(
    CreateAlipayAuthorizationRequestCommand command,
  ) => client.userAuthenticationChallengeCreateAlipayAuthorizationRequest(
    command,
    context: invocationContext(
      UserRequestPageIds.createAlipayAuthorizationRequest,
    ),
  );

  @override
  Future<OneTapLoginHint> resolveOneTapLoginHint(
    ResolveOneTapLoginHintCommand command,
  ) => client.userAuthenticationChallengeResolveOneTapLoginHint(
    command,
    context: invocationContext(UserRequestPageIds.resolveOneTapLoginHint),
  );
}
