import 'package:quwoquan_app/cloud/runtime/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef AccountSessionInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

/// AccountSession 登录、刷新与登出的 production generated-client adapter。
final class RemoteAccountSessionCommandWriter
    implements AccountSessionCommandWriter {
  const RemoteAccountSessionCommandWriter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final AccountSessionInvocationContextFactory invocationContext;

  @override
  Future<AuthSessionGrant> loginWithPhone(LoginWithPhoneCommand command) =>
      client.userAccountSessionLoginWithPhone(
        command,
        context: invocationContext(UserRequestPageIds.loginWithPhone),
      );

  @override
  Future<AuthSessionGrant> loginWithWechat(LoginWithWechatCommand command) =>
      client.userAccountSessionLoginWithWechat(
        command,
        context: invocationContext(UserRequestPageIds.loginWithWechat),
      );

  @override
  Future<AuthSessionGrant> loginWithAlipay(LoginWithAlipayCommand command) =>
      client.userAccountSessionLoginWithAlipay(
        command,
        context: invocationContext(UserRequestPageIds.loginWithAlipay),
      );

  @override
  Future<AuthSessionGrant> loginWithQq(LoginWithQqCommand command) =>
      client.userAccountSessionLoginWithQq(
        command,
        context: invocationContext(UserRequestPageIds.loginWithQq),
      );

  @override
  Future<AuthSessionGrant> loginOneTap(LoginOneTapCommand command) =>
      client.userAccountSessionLoginOneTap(
        command,
        context: invocationContext(UserRequestPageIds.loginOneTap),
      );

  @override
  Future<AuthSessionGrant> loginAnonymous(LoginAnonymousCommand command) =>
      client.userAccountSessionLoginAnonymous(
        command,
        context: invocationContext(UserRequestPageIds.loginAnonymous),
      );

  @override
  Future<TokenRefreshGrant> refreshToken(RefreshTokenCommand command) =>
      client.userAccountSessionRefreshToken(
        command,
        context: invocationContext(UserRequestPageIds.refreshToken),
      );

  @override
  Future<LogoutAck> logout(LogoutCommand command) =>
      client.userAccountSessionLogout(
        command,
        context: invocationContext(UserRequestPageIds.logout),
      );
}
