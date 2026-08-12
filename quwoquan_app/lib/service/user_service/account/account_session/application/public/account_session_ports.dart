import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show
        AuthSessionGrant,
        FederatedLoginOutcome,
        LoginAnonymousCommand,
        LoginOneTapCommand,
        LoginWithAlipayCommand,
        LoginWithPhoneCommand,
        LoginWithQqCommand,
        LoginWithWechatCommand,
        LogoutAck,
        LogoutCommand,
        IssueWhitelistedResearchSessionCommand,
        RefreshTokenCommand,
        TokenRefreshGrant,
        WhitelistedResearchSession;

/// AccountSession 的应用端登录写面。
abstract interface class AccountSessionLoginWriter {
  Future<AuthSessionGrant> loginWithPhone(LoginWithPhoneCommand command);

  Future<FederatedLoginOutcome> loginWithWechat(LoginWithWechatCommand command);

  Future<FederatedLoginOutcome> loginWithAlipay(LoginWithAlipayCommand command);

  Future<FederatedLoginOutcome> loginWithQq(LoginWithQqCommand command);

  Future<AuthSessionGrant> loginOneTap(LoginOneTapCommand command);

  Future<AuthSessionGrant> loginAnonymous(LoginAnonymousCommand command);
}

/// AccountSession 的应用端生命周期写面。
abstract interface class AccountSessionLifecycleWriter {
  Future<TokenRefreshGrant> refreshToken(RefreshTokenCommand command);

  Future<LogoutAck> logout(LogoutCommand command);
}

/// Alpha Research 身份签发写面；accountId 只来自已认证 invocation actor。
abstract interface class AccountSessionResearchIdentityWriter {
  Future<WhitelistedResearchSession> issueWhitelistedResearchSession(
    IssueWhitelistedResearchSessionCommand command,
  );
}

/// 同时承载登录与会话生命周期的对象级公开边界。
abstract interface class AccountSessionWriter
    implements
        AccountSessionLoginWriter,
        AccountSessionLifecycleWriter,
        AccountSessionResearchIdentityWriter {}
