import 'user_operation_contracts.g.dart';

abstract interface class AuthenticationChallengeCommandWriter {
  Future<OtpChallengeIssueResult> sendOtp(SendOtpCommand command);
  Future<AlipayAuthorizationGrant> createAlipayAuthorizationRequest(
    CreateAlipayAuthorizationRequestCommand command,
  );
  Future<OneTapLoginHint> resolveOneTapLoginHint(
    ResolveOneTapLoginHintCommand command,
  );
}
