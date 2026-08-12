import 'package:quwoquan_app/service/user_service/account/account_session/application/public/account_session_ports.dart';
import 'package:quwoquan_app/service/user_service/account/authentication_challenge/application/public/authentication_challenge_writer.dart';
import 'package:quwoquan_app/service/user_service/account/credential_binding/application/public/credential_binding_ports.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../runtime/fixtures/fixture_user_resolver.dart';

/// local_contract 专用对象级身份 Facet 组合，仅用于 Provider override。
///
/// production/Patrol composition 不得导入本文件；测试通过当前 AccountSession、
/// AuthenticationChallenge 与 CredentialBinding typed Facet 注入行为。
class TestAuthFacets
    implements
        AccountSessionWriter,
        AuthenticationChallengeWriter,
        CredentialBindingWriter,
        CredentialBindingReader {
  /// 身份单一真相源是 user-service canonical 场景，不在此处再抄一份常量：
  /// persona 与 user 是两个对象，硬编码同值会让「登录返回 metadata 当前身份」
  /// 这条契约在 persona 拆分后失真。
  static String get ownerId => FixtureUserResolver.currentUserVariantUserId;
  static String get personaId =>
      FixtureUserResolver.currentUserVariantPersonaId;

  @override
  Future<OtpDeliveryReadinessSnapshot> getOtpDeliveryReadiness() async {
    return const OtpDeliveryReadinessSnapshot(
      availability: OtpDeliveryReadinessAvailability.ready,
      retryAfterSeconds: 0,
    );
  }

  @override
  Future<OtpChallengeIssueResult> sendOtp(
    SendOtpCommand command, {
    required String idempotencyKey,
  }) async {
    final phone = command.phone;
    return OtpChallengeIssueResult(
      maskedPhone: phone.length > 7
          ? '${phone.substring(0, 3)}****${phone.substring(phone.length - 4)}'
          : phone,
      expiresInSeconds: 300,
      deliveryStatus: OtpDeliveryStatus.queued,
      retryAfterSeconds: 0,
      requestId: 'test_otp_request',
      challengeId: 'test_otp_challenge',
    );
  }

  @override
  Future<AlipayAuthorizationGrant> createAlipayAuthorizationRequest(
    CreateAlipayAuthorizationRequestCommand command,
  ) async {
    return AlipayAuthorizationGrant(
      authorizationPayload: 'test_alipay_authorization',
      expiresAt: DateTime.utc(2099),
    );
  }

  @override
  Future<OneTapLoginHint> resolveOneTapLoginHint(
    ResolveOneTapLoginHintCommand command,
  ) async {
    return const OneTapLoginHint(
      state: 'registered',
      maskedPhone: '180****3909',
      registered: true,
      expiresInSeconds: 60,
      providerRequestId: 'test_hint',
    );
  }

  @override
  Future<AuthSessionGrant> loginWithPhone(LoginWithPhoneCommand command) async {
    return loginGrant(identityOrigin: 'phone');
  }

  @override
  Future<AuthSessionGrant> loginOneTap(LoginOneTapCommand command) async {
    return loginGrant(identityOrigin: 'phone');
  }

  @override
  Future<FederatedLoginOutcome> loginWithWechat(
    LoginWithWechatCommand command,
  ) async {
    return FederatedLoginOutcome(
      status: FederatedLoginStatus.authenticated,
      session: loginGrant(identityOrigin: 'wechat'),
      expiresInSeconds: 0,
    );
  }

  @override
  Future<FederatedLoginOutcome> loginWithAlipay(
    LoginWithAlipayCommand command,
  ) async {
    return FederatedLoginOutcome(
      status: FederatedLoginStatus.authenticated,
      session: loginGrant(identityOrigin: 'alipay'),
      expiresInSeconds: 0,
    );
  }

  @override
  Future<FederatedLoginOutcome> loginWithQq(LoginWithQqCommand command) async {
    return FederatedLoginOutcome(
      status: FederatedLoginStatus.authenticated,
      session: loginGrant(identityOrigin: 'qq'),
      expiresInSeconds: 0,
    );
  }

  @override
  Future<AuthSessionGrant> loginAnonymous(LoginAnonymousCommand command) async {
    return loginGrant(identityOrigin: 'anonymous_device');
  }

  @override
  Future<TokenRefreshGrant> refreshToken(RefreshTokenCommand command) async {
    return const TokenRefreshGrant(
      accessToken: 'test_access_token',
      refreshToken: 'test_refresh_token',
      sessionRememberTtlSeconds: 0,
    );
  }

  @override
  Future<LogoutAck> logout(LogoutCommand command) async {
    return const LogoutAck(revoked: true);
  }

  @override
  Future<CredentialBindingCommandResult> bindPhoneCredential(
    BindPhoneCredentialCommand command,
  ) async {
    return CredentialBindingCommandResult(
      credentialType: CredentialType.phone,
      isActive: true,
      version: 1,
      idempotentReplay: false,
      displayLabel: command.displayLabel ?? _maskPhone(command.phone),
    );
  }

  @override
  Future<AuthSessionGrant> completeFederatedPhoneBinding(
    CompleteFederatedPhoneBindingCommand command,
  ) async {
    return loginGrant(identityOrigin: 'wechat');
  }

  @override
  Future<CredentialBindingCommandResult> bindCarrierPhoneCredential(
    BindCarrierPhoneCredentialCommand command,
  ) async {
    return CredentialBindingCommandResult(
      credentialType: CredentialType.carrierPhone,
      isActive: true,
      version: 1,
      idempotentReplay: false,
      displayLabel: command.displayLabel ?? '180****3909',
    );
  }

  @override
  Future<CredentialBindingCommandResult> unbindCredential(
    UnbindCredentialCommand command,
  ) async {
    return CredentialBindingCommandResult(
      credentialType: CredentialType.fromWire(
        command.credentialType,
        'UnbindCredentialCommand.credentialType',
      ),
      isActive: false,
      version: 2,
      idempotentReplay: false,
    );
  }

  @override
  Future<ListCredentialsSlice> listCredentials(
    ListCredentialsQuery query,
  ) async {
    return ListCredentialsSlice(
      credentials: <CredentialBindingView>[
        CredentialBindingView(
          id: 'test_credential',
          credentialType: CredentialType.phone,
          displayLabel: '180****3909',
          isActive: true,
          boundAt: DateTime.utc(2026),
          version: 1,
        ),
      ],
    );
  }

  AuthSessionGrant loginGrant({required String identityOrigin}) {
    return AuthSessionGrant(
      accessToken: 'test_access_token',
      refreshToken: 'test_refresh_token',
      ownerId: ownerId,
      activePersona: ActivePersonaEnvelope(personaId: personaId),
      personaCount: 1,
      accountState: identityOrigin == 'anonymous_device'
          ? 'anonymous'
          : 'active',
      identityOrigin: identityOrigin,
      logicalShard: 0,
      anonymousRetentionPolicy: '',
      sessionRememberTtlSeconds: 0,
    );
  }

  String _maskPhone(String phone) {
    return phone.length > 7
        ? '${phone.substring(0, 3)}****${phone.substring(phone.length - 4)}'
        : phone;
  }
}
