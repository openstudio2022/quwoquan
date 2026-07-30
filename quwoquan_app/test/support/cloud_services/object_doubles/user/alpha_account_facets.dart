import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Alpha-only AccountSession adapter；production 依赖图不可达本实现。
///
/// refresh token 在内存中执行 rotation；旧 token 被消费或登出后不可再次使用。
final class AlphaAccountSessionFacet implements AccountSessionCommandWriter {
  final Set<String> _refreshTokens = <String>{};
  int _sequence = 0;

  @override
  Future<AuthSessionGrant> loginWithPhone(
    LoginWithPhoneCommand command,
  ) async => _issueSession(
    identityOrigin: 'phone',
    accountHint: AccountHintSnapshot(
      displayName: 'Alpha Account',
      nicknameCustomized: false,
      avatarUrl: '',
      avatarAssetId: '',
      maskedPhone: _maskPhone(command.phone),
      identityOrigin: 'phone',
    ),
  );

  @override
  Future<FederatedLoginOutcome> loginWithWechat(
    LoginWithWechatCommand command,
  ) async => FederatedLoginOutcome.authenticated(
    _issueSession(identityOrigin: 'wechat'),
  );

  @override
  Future<FederatedLoginOutcome> loginWithAlipay(
    LoginWithAlipayCommand command,
  ) async => FederatedLoginOutcome.authenticated(
    _issueSession(identityOrigin: 'alipay'),
  );

  @override
  Future<FederatedLoginOutcome> loginWithQq(LoginWithQqCommand command) async =>
      FederatedLoginOutcome.authenticated(_issueSession(identityOrigin: 'qq'));

  @override
  Future<AuthSessionGrant> loginOneTap(LoginOneTapCommand command) async =>
      _issueSession(
        identityOrigin: 'carrier_phone',
        accountHint: const AccountHintSnapshot(
          displayName: 'Alpha Account',
          nicknameCustomized: false,
          avatarUrl: '',
          avatarAssetId: '',
          maskedPhone: '138****0000',
          identityOrigin: 'carrier_phone',
        ),
      );

  @override
  Future<AuthSessionGrant> loginAnonymous(
    LoginAnonymousCommand command,
  ) async => _issueSession(identityOrigin: 'anonymous_device');

  @override
  Future<TokenRefreshGrant> refreshToken(RefreshTokenCommand command) async {
    if (!_refreshTokens.remove(command.refreshToken)) {
      throw const AccountSessionTokenExpiredException();
    }
    final sequence = ++_sequence;
    final refreshToken = 'alpha-refresh-$sequence';
    _refreshTokens.add(refreshToken);
    return TokenRefreshGrant(
      accessToken: 'alpha-access-$sequence',
      refreshToken: refreshToken,
      sessionRememberTtlSeconds: _sessionRememberTtlSeconds,
    );
  }

  @override
  Future<LogoutAck> logout(LogoutCommand command) async {
    var revoked = false;
    final refreshToken = command.refreshToken?.trim() ?? '';
    if (refreshToken.isNotEmpty) {
      revoked = _refreshTokens.remove(refreshToken);
    } else {
      revoked = _refreshTokens.isNotEmpty;
      _refreshTokens.clear();
    }
    return LogoutAck(revoked: revoked);
  }

  AuthSessionGrant _issueSession({
    required String identityOrigin,
    AccountHintSnapshot? accountHint,
  }) {
    final sequence = ++_sequence;
    final refreshToken = 'alpha-refresh-$sequence';
    _refreshTokens.add(refreshToken);
    return AuthSessionGrant(
      accessToken: 'alpha-access-$sequence',
      refreshToken: refreshToken,
      ownerId: 'alpha-owner',
      accountState: 'active',
      identityOrigin: identityOrigin,
      logicalShard: 0,
      anonymousRetentionPolicy: identityOrigin == 'anonymous_device'
          ? 'device_bound'
          : 'retained',
      personaCount: 1,
      sessionRememberTtlSeconds: _sessionRememberTtlSeconds,
      activePersona: const ActivePersonaEnvelope(
        personaId: 'alpha-persona-primary',
      ),
      accountHint: accountHint,
    );
  }
}

/// Alpha-only AuthenticationChallenge adapter。
final class AlphaAuthenticationChallengeFacet
    implements AuthenticationChallengeCommandWriter {
  final Map<String, OneTapLoginHint> _oneTapHints = <String, OneTapLoginHint>{};
  int _sequence = 0;

  @override
  Future<OtpChallengeIssueResult> sendOtp(SendOtpCommand command) async {
    final sequence = ++_sequence;
    return OtpChallengeIssueResult(
      maskedPhone: _maskPhone(command.phone),
      expiresInSeconds: 300,
      deliveryStatus: 'queued',
      retryAfterSeconds: 60,
      requestId: 'alpha-otp-request-$sequence',
      challengeId: 'alpha-otp-challenge-$sequence',
    );
  }

  @override
  Future<AlipayAuthorizationGrant> createAlipayAuthorizationRequest(
    CreateAlipayAuthorizationRequestCommand command,
  ) async {
    final sequence = ++_sequence;
    return AlipayAuthorizationGrant(
      authorizationPayload: 'alpha-alipay-authorization-$sequence',
      expiresAt: DateTime.utc(2026, 12, 31).toIso8601String(),
    );
  }

  @override
  Future<OneTapLoginHint> resolveOneTapLoginHint(
    ResolveOneTapLoginHintCommand command,
  ) async {
    final key = '${command.vendor}:${command.carrierToken}';
    final existing = _oneTapHints[key];
    if (existing != null) return existing;
    final sequence = ++_sequence;
    final hint = OneTapLoginHint(
      state: 'ready',
      maskedPhone: '138****0000',
      registered: true,
      expiresInSeconds: 120,
      accountHint: const OneTapAccountHint(
        displayName: 'Alpha Account',
        avatarUrl: '',
        maskedPhone: '138****0000',
        identityOrigin: 'carrier_phone',
      ),
      providerRequestId: 'alpha-carrier-request-$sequence',
    );
    _oneTapHints[key] = hint;
    return hint;
  }
}

const int _sessionRememberTtlSeconds = 2592000;

String _maskPhone(String phone) {
  final normalized = phone.trim();
  if (normalized.length < 7) return '***';
  return '${normalized.substring(0, 3)}****'
      '${normalized.substring(normalized.length - 4)}';
}
