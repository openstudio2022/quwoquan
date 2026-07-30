import 'dart:convert';

import 'package:crypto/crypto.dart';
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
  Future<FederatedLoginOutcome> loginWithWechat(
    LoginWithWechatCommand command,
  ) => client.userAccountSessionLoginWithWechat(
    command,
    context: invocationContext(UserRequestPageIds.loginWithWechat),
  );

  @override
  Future<FederatedLoginOutcome> loginWithAlipay(
    LoginWithAlipayCommand command,
  ) => client.userAccountSessionLoginWithAlipay(
    command,
    context: invocationContext(UserRequestPageIds.loginWithAlipay),
  );

  @override
  Future<FederatedLoginOutcome> loginWithQq(LoginWithQqCommand command) =>
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
  Future<AuthSessionGrant> loginAnonymous(LoginAnonymousCommand command) {
    final base = invocationContext(UserRequestPageIds.loginAnonymous);
    return client.userAccountSessionLoginAnonymous(
      command,
      context: CloudOperationInvocationContext(
        surfaceId: base.surfaceId,
        clientPageId: base.clientPageId,
        actor: base.actor,
        routeId: base.routeId,
        referralSource: base.referralSource,
        feedRequestId: base.feedRequestId,
        shareId: base.shareId,
        modelId: base.modelId,
        experimentBucket: base.experimentBucket,
        idempotencyKey: _anonymousLoginIdempotencyKey(command),
        deadlineAt: base.deadlineAt,
        cancellation: base.cancellation,
      ),
    );
  }

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

String _anonymousLoginIdempotencyKey(LoginAnonymousCommand command) {
  final canonicalCommand = jsonEncode(<String, String>{
    'installId': command.installId,
    'deviceFingerprintHash': command.deviceFingerprintHash,
    'platform': command.platform,
    'appVersion': command.appVersion,
  });
  final digest = sha256.convert(utf8.encode(canonicalCommand));
  return 'login-anonymous-$digest';
}
