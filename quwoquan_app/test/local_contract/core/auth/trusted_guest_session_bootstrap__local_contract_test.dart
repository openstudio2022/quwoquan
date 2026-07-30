// spec_ref: specs/feature-tree/user-identity-profile-relationship/auth-profile-snapshot/spec.md#sit-001

import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/app/providers/startup_auth_restore_gate_provider.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart'
    show accountSessionLoginCommandWriterProvider;
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  test('匿名设备指纹保持既有 canonical 字节身份', () {
    expect(
      deriveAnonymousDeviceFingerprintHash('install-1'),
      'd7e2cc6057f3cbb1233d162744070d4c5a1afac3fb218c559cbf389ad888f605',
    );
  });

  test('首次正常启动单飞获取可信游客会话且不改变显式登录语义', () async {
    final store = _MemoryAuthSessionStore(_emptyStored());
    LoginAnonymousCommand? captured;
    var loginCalls = 0;
    final container = ProviderContainer(
      overrides: [
        startupAuthRestoreGateProvider.overrideWith(_OpenAuthGate.new),
        authSessionStoreProvider.overrideWithValue(store),
        accountSessionLoginCommandWriterProvider.overrideWithValue(
          _LoginWriter((command) async {
            loginCalls += 1;
            captured = command;
            return _anonymousGrant();
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    container.read(authSessionControllerProvider);
    await _waitUntil(
      () => container.read(authSessionControllerProvider).hasTrustedSession,
    );

    final state = container.read(authSessionControllerProvider);
    expect(loginCalls, 1);
    expect(captured?.installId, 'install-1');
    expect(
      captured?.deviceFingerprintHash,
      deriveAnonymousDeviceFingerprintHash('install-1'),
    );
    expect(state.isGuest, isTrue);
    expect(state.isAuthenticated, isFalse);
    expect(state.isAnonymousSession, isTrue);
    expect(state.hasTrustedSession, isTrue);
    expect(state.activePersonaId, 'anonymous-persona');
    expect(
      await container
          .read(authSessionControllerProvider.notifier)
          .accessTokenForRequest(),
      'anonymous-access',
    );
    http.Request? capturedRequest;
    final httpClient = CloudHttpClient(
      client: MockClient((request) async {
        capturedRequest = request;
        return http.Response('{}', 200);
      }),
      authTokenProvider: ProviderBackedCloudAuthTokenProvider(
        () => container
            .read(authSessionControllerProvider.notifier)
            .accessTokenForRequest(),
      ),
    );
    addTearDown(httpClient.close);
    await httpClient.get(Uri.parse('https://api.quwoquan.test/content/feed'));
    expect(
      capturedRequest?.headers['authorization'],
      'Bearer anonymous-access',
    );
  });

  test('恢复既有匿名 bearer 时不重复调用 LoginAnonymous', () async {
    var loginCalls = 0;
    final store = _MemoryAuthSessionStore(_storedFromGrant(_anonymousGrant()));
    final container = ProviderContainer(
      overrides: [
        startupAuthRestoreGateProvider.overrideWith(_OpenAuthGate.new),
        authSessionStoreProvider.overrideWithValue(store),
        accountSessionLoginCommandWriterProvider.overrideWithValue(
          _LoginWriter((_) async {
            loginCalls += 1;
            return _anonymousGrant();
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    container.read(authSessionControllerProvider);
    await _waitUntil(
      () => container.read(authSessionControllerProvider).hasTrustedSession,
    );

    final state = container.read(authSessionControllerProvider);
    expect(loginCalls, 0);
    expect(state.isGuest, isTrue);
    expect(state.isAuthenticated, isFalse);
    expect(state.isAnonymousSession, isTrue);
    expect(state.accessToken, 'anonymous-access');
  });

  test('并发业务请求共享同一个匿名登录 Future', () async {
    final loginStarted = Completer<void>();
    final loginResult = Completer<AuthSessionGrant>();
    var loginCalls = 0;
    final container = ProviderContainer(
      overrides: [
        authSessionStoreProvider.overrideWithValue(
          _MemoryAuthSessionStore(_emptyStored()),
        ),
        accountSessionLoginCommandWriterProvider.overrideWithValue(
          _LoginWriter((_) {
            loginCalls += 1;
            if (!loginStarted.isCompleted) {
              loginStarted.complete();
            }
            return loginResult.future;
          }),
        ),
      ],
    );
    addTearDown(container.dispose);
    final notifier = container.read(authSessionControllerProvider.notifier);

    final first = notifier.accessTokenForRequest();
    final second = notifier.accessTokenForRequest();
    await loginStarted.future;
    expect(loginCalls, 1);

    loginResult.complete(_anonymousGrant());
    expect(await Future.wait<String?>([first, second]), [
      'anonymous-access',
      'anonymous-access',
    ]);
    expect(loginCalls, 1);
  });

  test('匿名登录失败透传给业务请求且下一请求可以重试', () async {
    var loginCalls = 0;
    final failure = StateError('anonymous service unavailable');
    final container = ProviderContainer(
      overrides: [
        authSessionStoreProvider.overrideWithValue(
          _MemoryAuthSessionStore(_emptyStored()),
        ),
        accountSessionLoginCommandWriterProvider.overrideWithValue(
          _LoginWriter((_) async {
            loginCalls += 1;
            if (loginCalls == 1) {
              throw failure;
            }
            return _anonymousGrant();
          }),
        ),
      ],
    );
    addTearDown(container.dispose);
    final notifier = container.read(authSessionControllerProvider.notifier);

    await expectLater(notifier.accessTokenForRequest(), throwsA(same(failure)));
    final failed = container.read(authSessionControllerProvider);
    expect(failed.isGuest, isTrue);
    expect(failed.hasTrustedSession, isFalse);
    expect(failed.errorMessage, isNotEmpty);

    expect(await notifier.accessTokenForRequest(), 'anonymous-access');
    expect(loginCalls, 2);
  });

  test('正式登录开始后迟到的匿名结果不能覆盖正式会话', () async {
    final loginStarted = Completer<void>();
    final anonymousResult = Completer<AuthSessionGrant>();
    final store = _MemoryAuthSessionStore(_emptyStored());
    final container = ProviderContainer(
      overrides: [
        authSessionStoreProvider.overrideWithValue(store),
        accountSessionLoginCommandWriterProvider.overrideWithValue(
          _LoginWriter((_) {
            loginStarted.complete();
            return anonymousResult.future;
          }),
        ),
      ],
    );
    addTearDown(container.dispose);
    final notifier = container.read(authSessionControllerProvider.notifier);

    final pendingBearer = notifier.accessTokenForRequest();
    await loginStarted.future;
    await notifier.applyLoginGrant(_formalGrant());
    anonymousResult.complete(_anonymousGrant());

    expect(await pendingBearer, 'formal-access');
    final state = container.read(authSessionControllerProvider);
    expect(state.isAuthenticated, isTrue);
    expect(state.isGuest, isFalse);
    expect(state.isAnonymousSession, isFalse);
    expect(state.ownerId, 'formal-owner');
    expect(state.accessToken, 'formal-access');
    expect(store.stored.accessToken, 'formal-access');
    expect(store.stored.isAnonymousSession, isFalse);
  });

  test('可信游客会话与软退出正式账号的快速登录凭证分槽保存', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    FlutterSecureStorage.setMockInitialValues(<String, String>{});
    final store = AuthSessionStore();

    await store.saveLoginGrant(
      _formalGrant(),
      rememberedLoginMethod: AuthRememberedLoginMethod.phoneOtp,
      rememberedLoginMaskedIdentifier: '138****0001',
      rememberedLoginIdentifier: '13800000001',
    );
    await store.softLogout();
    await store.saveLoginGrant(
      _anonymousGrant(),
      rememberedLoginMethod: AuthRememberedLoginMethod.anonymous,
    );

    final stored = await store.read();
    expect(stored.accessToken, 'anonymous-access');
    expect(stored.refreshToken, 'anonymous-refresh');
    expect(stored.isAnonymousSession, isTrue);
    expect(stored.quickLoginRefreshToken, 'formal-refresh');
    expect(stored.hasValidQuickLoginCredential, isTrue);
    expect(stored.rememberedLoginMethod, AuthRememberedLoginMethod.phoneOtp);
    expect(stored.rememberedLoginMaskedIdentifier, '138****0001');
    expect(stored.manualLoggedOut, isTrue);
  });
}

final class _OpenAuthGate extends StartupAuthRestoreGateNotifier {
  @override
  bool build() => true;
}

final class _LoginWriter implements AccountSessionLoginCommandWriter {
  const _LoginWriter(this.loginAnonymousCallback);

  final Future<AuthSessionGrant> Function(LoginAnonymousCommand command)
  loginAnonymousCallback;

  @override
  Future<AuthSessionGrant> loginAnonymous(LoginAnonymousCommand command) =>
      loginAnonymousCallback(command);

  @override
  Future<AuthSessionGrant> loginOneTap(LoginOneTapCommand command) =>
      throw UnsupportedError('not used');

  @override
  Future<FederatedLoginOutcome> loginWithAlipay(
    LoginWithAlipayCommand command,
  ) => throw UnsupportedError('not used');

  @override
  Future<AuthSessionGrant> loginWithPhone(LoginWithPhoneCommand command) =>
      throw UnsupportedError('not used');

  @override
  Future<FederatedLoginOutcome> loginWithQq(LoginWithQqCommand command) =>
      throw UnsupportedError('not used');

  @override
  Future<FederatedLoginOutcome> loginWithWechat(
    LoginWithWechatCommand command,
  ) => throw UnsupportedError('not used');
}

final class _MemoryAuthSessionStore extends AuthSessionStore {
  _MemoryAuthSessionStore(this.stored);

  StoredAuthSession stored;

  @override
  Future<StoredAuthSession> read() async => stored;

  @override
  Future<void> saveLoginGrant(
    AuthSessionGrant result, {
    AuthRememberedLoginMethod rememberedLoginMethod =
        AuthRememberedLoginMethod.unknown,
    String? rememberedLoginMaskedIdentifier,
    String? rememberedLoginIdentifier,
  }) async {
    stored = _storedFromGrant(
      result,
      previous: stored,
      rememberedLoginMethod: rememberedLoginMethod,
      rememberedLoginMaskedIdentifier: rememberedLoginMaskedIdentifier,
      rememberedLoginIdentifier: rememberedLoginIdentifier,
    );
  }
}

StoredAuthSession _emptyStored() => const StoredAuthSession(
  accessToken: '',
  refreshToken: '',
  ownerId: '',
  activePersonaId: '',
  accountState: '',
  identityOrigin: '',
  installId: 'install-1',
  manualLoggedOut: false,
  launchPromptDismissed: true,
);

StoredAuthSession _storedFromGrant(
  AuthSessionGrant grant, {
  StoredAuthSession? previous,
  AuthRememberedLoginMethod rememberedLoginMethod =
      AuthRememberedLoginMethod.unknown,
  String? rememberedLoginMaskedIdentifier,
  String? rememberedLoginIdentifier,
}) {
  final isAnonymousSession = grant.accountState.trim() == 'anonymous';
  return StoredAuthSession(
    accessToken: grant.accessToken,
    refreshToken: grant.refreshToken,
    ownerId: grant.ownerId,
    activePersonaId: grant.activePersona?.personaId ?? '',
    accountState: grant.accountState,
    identityOrigin: grant.identityOrigin,
    installId: previous?.installId ?? 'install-1',
    lastRefreshAtEpochMs: DateTime.now().millisecondsSinceEpoch,
    lastForegroundAuthCheckAtEpochMs: DateTime.now().millisecondsSinceEpoch,
    rememberedLoginMethod: isAnonymousSession
        ? previous?.rememberedLoginMethod ?? AuthRememberedLoginMethod.unknown
        : rememberedLoginMethod,
    rememberedLoginMaskedIdentifier: isAnonymousSession
        ? previous?.rememberedLoginMaskedIdentifier ?? ''
        : rememberedLoginMaskedIdentifier ?? '',
    rememberedLoginIdentifier: isAnonymousSession
        ? previous?.rememberedLoginIdentifier ?? ''
        : rememberedLoginIdentifier ?? '',
    rememberedDisplayName: isAnonymousSession
        ? previous?.rememberedDisplayName ?? ''
        : grant.accountHint?.displayName ?? '',
    rememberedAvatarUrl: isAnonymousSession
        ? previous?.rememberedAvatarUrl ?? ''
        : grant.accountHint?.avatarUrl ?? '',
    rememberedNicknameCustomized: isAnonymousSession
        ? previous?.rememberedNicknameCustomized ?? false
        : grant.accountHint?.nicknameCustomized ?? false,
    rememberedRefreshToken: isAnonymousSession
        ? previous?.rememberedRefreshToken ?? ''
        : '',
    quickLoginExpiresAtEpochMs: isAnonymousSession
        ? previous?.quickLoginExpiresAtEpochMs ?? 0
        : 0,
    manualLoggedOut: isAnonymousSession
        ? previous?.manualLoggedOut ?? false
        : false,
    launchPromptDismissed: isAnonymousSession
        ? previous?.launchPromptDismissed ?? true
        : false,
  );
}

AuthSessionGrant _anonymousGrant() => const AuthSessionGrant(
  accessToken: 'anonymous-access',
  refreshToken: 'anonymous-refresh',
  ownerId: 'anonymous-owner',
  accountState: 'anonymous',
  identityOrigin: 'anonymous_device',
  logicalShard: 1,
  anonymousRetentionPolicy: 'preserve',
  personaCount: 1,
  sessionRememberTtlSeconds: 2592000,
  activePersona: ActivePersonaEnvelope(personaId: 'anonymous-persona'),
);

AuthSessionGrant _formalGrant() => const AuthSessionGrant(
  accessToken: 'formal-access',
  refreshToken: 'formal-refresh',
  ownerId: 'formal-owner',
  accountState: 'active',
  identityOrigin: 'anonymous_device',
  logicalShard: 2,
  anonymousRetentionPolicy: 'preserve',
  personaCount: 1,
  sessionRememberTtlSeconds: 2592000,
  activePersona: ActivePersonaEnvelope(personaId: 'formal-persona'),
);

Future<void> _waitUntil(bool Function() predicate) async {
  final deadline = DateTime.now().add(const Duration(seconds: 2));
  while (!predicate()) {
    if (DateTime.now().isAfter(deadline)) {
      throw TimeoutException('condition not reached');
    }
    await Future<void>.delayed(const Duration(milliseconds: 5));
  }
}
