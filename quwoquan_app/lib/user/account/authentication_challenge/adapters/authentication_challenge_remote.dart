import 'package:quwoquan_app/cloud/runtime/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef AuthenticationChallengeInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

/// AuthenticationChallenge 的 production generated-client adapter。
final class RemoteAuthenticationChallengeCommandWriter
    implements AuthenticationChallengeCommandWriter {
  const RemoteAuthenticationChallengeCommandWriter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final AuthenticationChallengeInvocationContextFactory invocationContext;

  @override
  Future<OtpChallengeIssueResult> sendOtp(SendOtpCommand command) =>
      client.userAuthenticationChallengeSendOtp(
        command,
        context: invocationContext(UserRequestPageIds.sendOtp),
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
