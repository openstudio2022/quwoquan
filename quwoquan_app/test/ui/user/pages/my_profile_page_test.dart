import 'dart:async';
import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/auth_login_result_dto.g.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/cloud/services/user/user_profile_repository.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/user/pages/my_profile_page.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_shell.dart';

/// 返回透明 1x1 PNG，避免 NetworkImage 产生 pending timer。
class _FakeHttpOverrides extends HttpOverrides {
  @override
  HttpClient createHttpClient(SecurityContext? context) => _FakeHttpClient();
}

class _FakeHttpClient implements HttpClient {
  @override
  bool autoUncompress = true;
  @override
  Duration? connectionTimeout;
  @override
  Duration idleTimeout = const Duration(seconds: 15);
  @override
  int? maxConnectionsPerHost;
  @override
  String? userAgent;
  @override
  void addCredentials(
    Uri url,
    String realm,
    HttpClientCredentials credentials,
  ) {}
  @override
  void addProxyCredentials(
    String host,
    int port,
    String realm,
    HttpClientCredentials credentials,
  ) {}
  @override
  set authenticate(Future<bool> Function(Uri, String, String?)? f) {}
  @override
  set authenticateProxy(
    Future<bool> Function(String, int, String, String?)? f,
  ) {}
  @override
  set badCertificateCallback(
    bool Function(X509Certificate, String, int)? callback,
  ) {}
  @override
  set connectionFactory(
    Future<ConnectionTask<Socket>> Function(Uri, String?, int?)? f,
  ) {}
  @override
  set findProxy(String Function(Uri)? f) {}
  @override
  set keyLog(Function(String)? callback) {}
  @override
  void close({bool force = false}) {}
  @override
  Future<HttpClientRequest> open(
    String method,
    String host,
    int port,
    String path,
  ) => _fakeRequest();
  @override
  Future<HttpClientRequest> openUrl(String method, Uri url) => _fakeRequest();
  @override
  Future<HttpClientRequest> get(String host, int port, String path) =>
      _fakeRequest();
  @override
  Future<HttpClientRequest> getUrl(Uri url) => _fakeRequest();
  @override
  Future<HttpClientRequest> post(String host, int port, String path) =>
      _fakeRequest();
  @override
  Future<HttpClientRequest> postUrl(Uri url) => _fakeRequest();
  @override
  Future<HttpClientRequest> put(String host, int port, String path) =>
      _fakeRequest();
  @override
  Future<HttpClientRequest> putUrl(Uri url) => _fakeRequest();
  @override
  Future<HttpClientRequest> delete(String host, int port, String path) =>
      _fakeRequest();
  @override
  Future<HttpClientRequest> deleteUrl(Uri url) => _fakeRequest();
  @override
  Future<HttpClientRequest> head(String host, int port, String path) =>
      _fakeRequest();
  @override
  Future<HttpClientRequest> headUrl(Uri url) => _fakeRequest();
  @override
  Future<HttpClientRequest> patch(String host, int port, String path) =>
      _fakeRequest();
  @override
  Future<HttpClientRequest> patchUrl(Uri url) => _fakeRequest();
  Future<HttpClientRequest> _fakeRequest() =>
      Future.value(_FakeHttpClientRequest());
}

class _FakeHttpClientRequest extends Fake implements HttpClientRequest {
  @override
  HttpHeaders get headers => _FakeHttpHeaders();
  @override
  Future<HttpClientResponse> close() => Future.value(_FakeHttpClientResponse());
}

class _FakeHttpHeaders extends Fake implements HttpHeaders {}

class _FakeHttpClientResponse extends Fake implements HttpClientResponse {
  static const _kTransparentPng = [
    0x89,
    0x50,
    0x4E,
    0x47,
    0x0D,
    0x0A,
    0x1A,
    0x0A,
    0x00,
    0x00,
    0x00,
    0x0D,
    0x49,
    0x48,
    0x44,
    0x52,
    0x00,
    0x00,
    0x00,
    0x01,
    0x00,
    0x00,
    0x00,
    0x01,
    0x08,
    0x06,
    0x00,
    0x00,
    0x00,
    0x1F,
    0x15,
    0xC4,
    0x89,
    0x00,
    0x00,
    0x00,
    0x0A,
    0x49,
    0x44,
    0x41,
    0x54,
    0x78,
    0x9C,
    0x62,
    0x00,
    0x00,
    0x00,
    0x02,
    0x00,
    0x01,
    0xE5,
    0x27,
    0xDE,
    0xFC,
    0x00,
    0x00,
    0x00,
    0x00,
    0x49,
    0x45,
    0x4E,
    0x44,
    0xAE,
    0x42,
    0x60,
    0x82,
  ];
  @override
  int get statusCode => 200;
  @override
  int get contentLength => _kTransparentPng.length;
  @override
  HttpClientResponseCompressionState get compressionState =>
      HttpClientResponseCompressionState.notCompressed;
  @override
  StreamSubscription<List<int>> listen(
    void Function(List<int>)? onData, {
    Function? onError,
    void Function()? onDone,
    bool? cancelOnError,
  }) {
    return Stream<List<int>>.fromIterable([_kTransparentPng]).listen(
      onData,
      onError: onError,
      onDone: onDone,
      cancelOnError: cancelOnError,
    );
  }
}

class _ThrowingCapabilityRepository extends RelationshipCapabilityRepository {
  @override
  bool get reconcilesCapabilityWithSharedRelationshipState => false;

  @override
  Future<RelationshipCapabilityDto> getCapability(String targetUserId) {
    return Future.error(StateError('capability unavailable in test'));
  }
}

class _TestAuthSessionStore implements AuthSessionStore {
  const _TestAuthSessionStore({required this.authenticated});

  final bool authenticated;

  @override
  Future<StoredAuthSession> read() async {
    return StoredAuthSession(
      accessToken: authenticated ? 'access-token' : '',
      refreshToken: authenticated ? 'refresh-token' : '',
      ownerId: authenticated ? 'user_001' : '',
      activeSubAccountId: authenticated ? 'user_001' : '',
      accountState: authenticated ? 'active' : '',
      identityOrigin: authenticated ? 'phone' : '',
      installId: 'install-id',
      lastRefreshAtEpochMs: 0,
      lastForegroundAuthCheckAtEpochMs: 0,
      manualLoggedOut: false,
      launchPromptDismissed: !authenticated,
    );
  }

  @override
  Future<void> saveLoginResult(
    AuthLoginResultDto result, {
    AuthRememberedLoginMethod rememberedLoginMethod =
        AuthRememberedLoginMethod.unknown,
    String? rememberedLoginMaskedIdentifier,
    String? rememberedLoginIdentifier,
  }) async {}

  @override
  Future<void> saveRefreshedTokens({
    required String accessToken,
    required String refreshToken,
  }) async {}

  @override
  Future<void> updateActiveSubAccount(String subAccountId) async {}

  @override
  Future<void> clearSession({required bool manualLogout}) async {}

  @override
  Future<void> softLogout() async {}

  @override
  Future<void> markLaunchPromptDismissed() async {}

  @override
  Future<void> markForegroundAuthCheckNow() async {}
}

void main() {
  setUp(() {
    HttpOverrides.global = _FakeHttpOverrides();
  });

  Widget buildTestApp() {
    return ProviderScope(
      overrides: [
        userProfileRepositoryProvider.overrideWithValue(
          const MockUserProfileRepository(),
        ),
        relationshipCapabilityRepositoryProvider.overrideWithValue(
          _ThrowingCapabilityRepository(),
        ),
        currentUserIdProvider.overrideWithValue('user_001'),
        authSessionStoreProvider.overrideWithValue(
          const _TestAuthSessionStore(authenticated: true),
        ),
      ],
      child: const MaterialApp(home: MyProfilePage()),
    );
  }

  Widget buildTestAppWithOverrides(List overrides) {
    return ProviderScope(
      overrides: [
        userProfileRepositoryProvider.overrideWithValue(
          const MockUserProfileRepository(),
        ),
        relationshipCapabilityRepositoryProvider.overrideWithValue(
          _ThrowingCapabilityRepository(),
        ),
        authSessionStoreProvider.overrideWithValue(
          const _TestAuthSessionStore(authenticated: true),
        ),
        ...overrides,
      ],
      child: const MaterialApp(home: MyProfilePage()),
    );
  }

  Future<void> pumpUntilLoaded(WidgetTester tester) async {
    for (var i = 0; i < 25; i++) {
      await tester.pump(const Duration(milliseconds: 100));
      if (find.text('趣我圈用户').evaluate().isNotEmpty) break;
    }
  }

  void setPhoneSize(WidgetTester tester) {
    tester.view.physicalSize = const Size(1080, 2400);
    tester.view.devicePixelRatio = 3.0;
  }

  group('MyProfilePage — 我的主页数据加载 (A1)', () {
    testWidgets('未登录态展示完整主页占位与登录按钮', (tester) async {
      setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            userProfileRepositoryProvider.overrideWithValue(
              const MockUserProfileRepository(),
            ),
            relationshipCapabilityRepositoryProvider.overrideWithValue(
              _ThrowingCapabilityRepository(),
            ),
            authSessionStoreProvider.overrideWithValue(
              const _TestAuthSessionStore(authenticated: false),
            ),
          ],
          child: const MaterialApp(home: MyProfilePage()),
        ),
      );
      await tester.pumpAndSettle();

      expect(
        find.text(UITextConstants.profileLoggedOutDisplayName),
        findsOneWidget,
      );
      expect(find.text(UITextConstants.profileLoginNow), findsOneWidget);
      expect(
        find.text(UITextConstants.profileLoggedOutTimelineHint),
        findsOneWidget,
      );
    });

    testWidgets('进入后 displayName 非 "me"，展示真实昵称', (tester) async {
      setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(buildTestApp());
      await pumpUntilLoaded(tester);

      expect(find.text('me'), findsNothing);
      expect(find.text('趣我圈用户'), findsAtLeastNWidgets(1));
    });

    testWidgets('avatar 与 background 正确展示', (tester) async {
      setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(buildTestApp());
      await pumpUntilLoaded(tester);

      expect(find.byType(ProfileShell), findsOneWidget);
      expect(find.byType(CircleAvatar), findsAtLeastNWidgets(1));
    });

    testWidgets('我的页顶栏展示全局搜索与小趣入口', (tester) async {
      setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(buildTestApp());
      await pumpUntilLoaded(tester);

      expect(find.byKey(TestKeys.globalSearchLauncherButton), findsOneWidget);
      expect(find.byIcon(CupertinoIcons.sparkles), findsAtLeastNWidgets(1));
      expect(
        tester.getSize(find.byKey(TestKeys.globalAssistantEntryMark)),
        const Size.square(AppSpacing.globalAssistantEntryMarkSize),
      );
    });

    testWidgets('currentUserIdProvider 可 override 用于测试', (tester) async {
      setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(
        buildTestAppWithOverrides([
          currentUserIdProvider.overrideWithValue('nature_photographer'),
        ]),
      );
      await pumpUntilLoaded(tester);

      expect(find.text('自然摄影师'), findsAtLeastNWidgets(1));
    });
  });
}
