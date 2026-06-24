import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/providers/appearance_settings_provider.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/auth_login_result_dto.g.dart';
import 'package:quwoquan_app/cloud/services/user/appearance_settings_repository.dart';
import 'package:quwoquan_app/cloud/services/user/auth_repository.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/constants/app_concept_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/providers/theme_provider.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/settings/pages/settings_about_page.dart';
import 'package:quwoquan_app/ui/settings/pages/settings_page.dart';
import 'package:quwoquan_app/ui/settings/pages/settings_permissions_page.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    PackageInfo.setMockInitialValues(
      appName: UITextConstants.loginBrandName,
      packageName: 'com.quwoquan.app',
      version: UITextConstants.settingsAboutDefaultVersion,
      buildNumber: '1',
      buildSignature: '',
    );
  });

  group('SettingsPage 我的主页设置页', () {
    testWidgets('仅展示新设置 IA 指定入口', (tester) async {
      _useTallViewport(tester);
      await tester.pumpWidget(_buildSettingsApp());
      await tester.pumpAndSettle();

      expect(find.text(UITextConstants.profileEditLabel), findsOneWidget);
      expect(find.text(UITextConstants.profilePersonasLabel), findsOneWidget);
      expect(
        find.text(UITextConstants.settingsPermissionManagement),
        findsOneWidget,
      );
      expect(find.text(UITextConstants.settingsDarkMode), findsOneWidget);
      expect(find.text(UITextConstants.settingsAboutQuwoquan), findsOneWidget);
      expect(find.text(UITextConstants.switchAccount), findsOneWidget);
      expect(find.text(UITextConstants.logout), findsOneWidget);

      expect(find.text(AppConceptConstants.assistantLabel), findsNothing);
      expect(find.text(SettingsRemovedText.notification), findsNothing);
      expect(find.text(SettingsRemovedText.cache), findsNothing);
      expect(find.text(SettingsRemovedText.developer), findsNothing);
      expect(find.text(SettingsRemovedText.preferenceSection), findsNothing);
      expect(find.text(SettingsRemovedText.appearanceAndFont), findsNothing);
      expect(
        find.text(SettingsRemovedText.assistantContentAccess),
        findsNothing,
      );
      expect(find.text(SettingsRemovedText.accountSecurity), findsNothing);
      expect(find.text(SettingsRemovedText.loginCredentials), findsNothing);
      expect(find.text(SettingsRemovedText.loginDevices), findsNothing);
      expect(find.text(SettingsRemovedText.accountDeletion), findsNothing);
      expect(find.text(SettingsRemovedText.dataRights), findsNothing);
      expect(find.text(SettingsRemovedText.userAndPersona), findsNothing);
    });

    testWidgets('编辑资料和分身管理进入既有路由', (tester) async {
      await tester.pumpWidget(_buildSettingsApp());
      await tester.pumpAndSettle();

      await tester.tap(find.text(UITextConstants.profileEditLabel));
      await tester.pumpAndSettle();
      expect(find.text(_RouteProbe.profileEdit), findsOneWidget);

      final router = GoRouter.of(
        tester.element(find.text(_RouteProbe.profileEdit)),
      );
      router.go(AppRoutePaths.settings);
      await tester.pumpAndSettle();

      await tester.tap(find.text(UITextConstants.profilePersonasLabel));
      await tester.pumpAndSettle();
      expect(find.text(_RouteProbe.profilePersonas), findsOneWidget);
    });

    testWidgets('权限管理页展示三层预留权限', (tester) async {
      await tester.pumpWidget(_buildSettingsApp());
      await tester.pumpAndSettle();

      await tester.tap(find.text(UITextConstants.settingsPermissionManagement));
      await tester.pumpAndSettle();

      expect(find.byType(SettingsPermissionsPage), findsOneWidget);
      expect(
        find.text(UITextConstants.settingsContactsPermission),
        findsOneWidget,
      );
      expect(
        find.text(UITextConstants.settingsCirclesPermission),
        findsOneWidget,
      );
      expect(
        find.text(UITextConstants.settingsEntitiesPermission),
        findsOneWidget,
      );
      expect(
        find.text(UITextConstants.settingsPermissionReserved),
        findsNWidgets(3),
      );
    });

    testWidgets('深色模式 Sheet 只有关闭、打开、跟随系统并更新运行时', (tester) async {
      await tester.pumpWidget(_buildSettingsApp());
      await tester.pumpAndSettle();

      await tester.tap(find.text(UITextConstants.settingsDarkMode));
      await tester.pumpAndSettle();

      expect(find.text(UITextConstants.settingsDarkModeOff), findsOneWidget);
      expect(find.text(UITextConstants.settingsDarkModeOn), findsOneWidget);
      expect(find.text(UITextConstants.settingsDarkModeSystem), findsWidgets);

      await tester.tap(find.text(UITextConstants.settingsDarkModeOn));
      await tester.pumpAndSettle();

      final container = ProviderScope.containerOf(
        tester.element(find.byType(SettingsPage)),
      );
      expect(
        container.read(themeProvider).themeModeSetting,
        AppThemeModeSetting.dark,
      );
      expect(
        container.read(appearanceSettingsControllerProvider).snapshot.themeMode,
        AppearanceThemeMode.dark,
      );
    });

    testWidgets('关于趣我圈页显示版本号', (tester) async {
      await tester.pumpWidget(_buildSettingsApp());
      await tester.pumpAndSettle();

      await tester.tap(find.text(UITextConstants.settingsAboutQuwoquan));
      await tester.pumpAndSettle();

      expect(find.byType(SettingsAboutPage), findsOneWidget);
      expect(find.text(UITextConstants.loginBrandName), findsWidgets);
      expect(find.text(UITextConstants.settingsVersion), findsOneWidget);
      expect(
        find.text(
          UITextConstants.settingsVersionValue(
            UITextConstants.settingsAboutDefaultVersion,
          ),
        ),
        findsOneWidget,
      );
    });

    testWidgets('退出登录默认走软退出：不远端吊销、不清本机凭证', (tester) async {
      final store = _SpyAuthSessionStore();
      final repo = _SpyAuthRepository();
      await tester.pumpWidget(
        _buildSettingsApp(store: store, authRepository: repo),
      );
      await tester.pumpAndSettle();

      await _openLogoutSheet(tester);

      expect(
        find.widgetWithText(
          CupertinoActionSheetAction,
          UITextConstants.logoutSoftAction,
        ),
        findsOneWidget,
      );
      expect(
        find.widgetWithText(
          CupertinoActionSheetAction,
          UITextConstants.logoutHardAction,
        ),
        findsOneWidget,
      );

      await tester.tap(
        find.widgetWithText(
          CupertinoActionSheetAction,
          UITextConstants.logoutSoftAction,
        ),
      );
      await tester.pumpAndSettle();

      expect(store.softLogoutCount, 1);
      expect(store.clearSessionCount, 0);
      expect(repo.logoutCount, 0);
      await tester.pump(const Duration(seconds: 4));
    });

    testWidgets('退出并清除本机登录信息：远端吊销 + 清本机凭证', (tester) async {
      final store = _SpyAuthSessionStore();
      final repo = _SpyAuthRepository();
      await tester.pumpWidget(
        _buildSettingsApp(store: store, authRepository: repo),
      );
      await tester.pumpAndSettle();

      await _openLogoutSheet(tester);

      await tester.tap(
        find.widgetWithText(
          CupertinoActionSheetAction,
          UITextConstants.logoutHardAction,
        ),
      );
      await tester.pumpAndSettle();

      expect(repo.logoutCount, 1);
      expect(store.clearSessionCount, 1);
      expect(store.softLogoutCount, 0);
      await tester.pump(const Duration(seconds: 4));
    });
  });
}

Future<void> _openLogoutSheet(WidgetTester tester) async {
  _useTallViewport(tester);
  await tester.pumpAndSettle();

  await tester.tap(find.text(UITextConstants.logout));
  await tester.pumpAndSettle();
}

void _useTallViewport(WidgetTester tester) {
  tester.view.physicalSize = const Size(1200, 4000);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
}

Widget _buildSettingsApp({
  AuthSessionStore? store,
  AuthRepository? authRepository,
}) {
  return ProviderScope(
    overrides: [
      appearanceSettingsRepositoryProvider.overrideWithValue(
        MockAppearanceSettingsRepository(),
      ),
      authSessionStoreProvider.overrideWithValue(
        store ?? _SpyAuthSessionStore(),
      ),
      if (authRepository != null)
        authRepositoryProvider.overrideWithValue(authRepository),
    ],
    child: MaterialApp.router(
      routerConfig: GoRouter(
        initialLocation: AppRoutePaths.settings,
        routes: [
          GoRoute(
            path: AppRoutePaths.settings,
            builder: (context, state) => const SettingsPage(),
            routes: [
              GoRoute(
                path: AppRoutePaths.settingsPermissionsSegment,
                builder: (context, state) => const SettingsPermissionsPage(),
              ),
              GoRoute(
                path: AppRoutePaths.settingsAboutSegment,
                builder: (context, state) => const SettingsAboutPage(),
              ),
            ],
          ),
          GoRoute(
            path: AppRoutePaths.profileEdit,
            builder: (context, state) => const Text(_RouteProbe.profileEdit),
          ),
          GoRoute(
            path: AppRoutePaths.profilePersonas,
            builder: (context, state) =>
                const Text(_RouteProbe.profilePersonas),
          ),
          GoRoute(
            path: AppRoutePaths.loginPathTemplate,
            builder: (context, state) => const Text(_RouteProbe.login),
          ),
        ],
      ),
    ),
  );
}

abstract final class _RouteProbe {
  static const String profileEdit = 'profile-edit-route';
  static const String profilePersonas = 'profile-personas-route';
  static const String login = 'login-route';
}

abstract final class SettingsRemovedText {
  static const String notification = '通知';
  static const String cache = '存储与缓存';
  static const String developer = '开发者';
  static const String preferenceSection = '偏好';
  static const String appearanceAndFont = '外观与字号';
  static const String assistantContentAccess = '私助读取创作内容';
  static const String accountSecurity = '账号安全与隐私';
  static const String loginCredentials = '登录方式与凭证';
  static const String loginDevices = '登录设备与会话';
  static const String accountDeletion = '账号注销与恢复';
  static const String dataRights = '数据导出与撤回同意';
  static const String userAndPersona = '用户与分身';
}

class _SpyAuthSessionStore implements AuthSessionStore {
  int softLogoutCount = 0;
  int clearSessionCount = 0;

  @override
  Future<StoredAuthSession> read() async => StoredAuthSession(
    accessToken: 'access-token',
    refreshToken: 'refresh-token',
    ownerId: 'owner-id',
    activeSubAccountId: 'sub-id',
    accountState: 'active',
    identityOrigin: 'phone',
    installId: 'install-id',
    lastRefreshAtEpochMs: DateTime.now().millisecondsSinceEpoch,
    lastForegroundAuthCheckAtEpochMs: DateTime.now().millisecondsSinceEpoch,
    manualLoggedOut: false,
    launchPromptDismissed: true,
  );

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
  Future<void> clearSession({required bool manualLogout}) async {
    clearSessionCount += 1;
  }

  @override
  Future<void> softLogout() async {
    softLogoutCount += 1;
  }

  @override
  Future<void> markLaunchPromptDismissed() async {}

  @override
  Future<void> markForegroundAuthCheckNow() async {}
}

class _SpyAuthRepository extends MockAuthRepository {
  int logoutCount = 0;

  @override
  Future<void> logout({String? refreshToken, String? deviceId}) async {
    logoutCount += 1;
  }
}
