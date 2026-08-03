import 'user_operation_contracts.g.dart';

/// AccountSession 的应用端登录写面。
abstract interface class AccountSessionLoginCommandWriter {
  Future<AuthSessionGrant> loginWithPhone(LoginWithPhoneCommand command);
  Future<FederatedLoginOutcome> loginWithWechat(LoginWithWechatCommand command);
  Future<FederatedLoginOutcome> loginWithAlipay(LoginWithAlipayCommand command);
  Future<FederatedLoginOutcome> loginWithQq(LoginWithQqCommand command);
  Future<AuthSessionGrant> loginOneTap(LoginOneTapCommand command);
  Future<AuthSessionGrant> loginAnonymous(LoginAnonymousCommand command);
}

/// AccountSession 的应用端生命周期写面。
abstract interface class AccountSessionLifecycleCommandWriter {
  Future<TokenRefreshGrant> refreshToken(RefreshTokenCommand command);
  Future<LogoutAck> logout(LogoutCommand command);
}

abstract interface class AccountSessionCommandWriter
    implements
        AccountSessionLoginCommandWriter,
        AccountSessionLifecycleCommandWriter {}
