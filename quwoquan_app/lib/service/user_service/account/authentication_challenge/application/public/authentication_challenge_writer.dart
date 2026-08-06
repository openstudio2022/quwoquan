import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show
        AlipayAuthorizationGrant,
        CreateAlipayAuthorizationRequestCommand,
        OneTapLoginHint,
        OtpChallengeIssueResult,
        ResolveOneTapLoginHintCommand,
        SendOtpCommand;

abstract interface class AuthenticationChallengeWriter {
  Future<OtpChallengeIssueResult> sendOtp(SendOtpCommand command);

  Future<AlipayAuthorizationGrant> createAlipayAuthorizationRequest(
    CreateAlipayAuthorizationRequestCommand command,
  );

  Future<OneTapLoginHint> resolveOneTapLoginHint(
    ResolveOneTapLoginHintCommand command,
  );
}
