import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:fluentui_system_icons/fluentui_system_icons.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/shell/bottom_navigation.dart';
import 'package:quwoquan_app/app/shell/main_app_shell.dart';
import 'package:quwoquan_app/app/shell/web_app_install_banner.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/auth_login_result_dto.g.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/constants/app_concept_constants.dart';
import 'package:quwoquan_app/core/constants/settings_semantic_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/icons/app_custom_icons.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/platform/platform_capabilities.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/l10n/l10n.dart';
import 'package:quwoquan_app/ui/discovery/pages/home_page.dart';
import 'package:shared_preferences/shared_preferences.dart';

Widget _buildShell(String location, {bool authenticated = true}) {
  return ProviderScope(
    overrides: [
      authSessionStoreProvider.overrideWithValue(
        _TestAuthSessionStore(authenticated: authenticated),
      ),
    ],
    child: MaterialApp(
      localizationsDelegates: const [
        AppLocalizations.delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      supportedLocales: const [Locale('zh', 'CN'), Locale('en', 'US')],
      home: MainAppShell(
        currentLocation: location,
        child: const SizedBox.shrink(),
      ),
    ),
  );
}

Widget _buildDarkShell(String location, {bool authenticated = true}) {
  return ProviderScope(
    overrides: [
      isDarkProvider.overrideWith((ref) => true),
      authSessionStoreProvider.overrideWithValue(
        _TestAuthSessionStore(authenticated: authenticated),
      ),
    ],
    child: MaterialApp(
      localizationsDelegates: const [
        AppLocalizations.delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      supportedLocales: const [Locale('zh', 'CN'), Locale('en', 'US')],
      home: MainAppShell(
        currentLocation: location,
        child: const SizedBox.shrink(),
      ),
    ),
  );
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
      manualLoggedOut: false,
      launchPromptDismissed: !authenticated,
    );
  }

  @override
  Future<void> saveLoginResult(AuthLoginResultDto result) async {}

  @override
  Future<void> updateActiveSubAccount(String subAccountId) async {}

  @override
  Future<void> clearSession({required bool manualLogout}) async {}

  @override
  Future<void> markLaunchPromptDismissed() async {}
}

void _suppressExpectedErrors() {
  final original = FlutterError.onError;
  FlutterError.onError = (details) {
    final message = details.exceptionAsString();
    if (message.contains('HTTP request failed') ||
        message.contains('NetworkImageLoadException') ||
        message.contains('overflowed')) {
      return;
    }
    original?.call(details);
  };
}

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues(const <String, Object>{});
  });

  group('MainAppShell', () {
    testWidgets('底部导航展示五栏，精品成为独立一级入口', (tester) async {
      _suppressExpectedErrors();
      await tester.pumpWidget(_buildShell(AppRoutePaths.home));
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.text('首页'), findsWidgets);
      expect(find.text('精品'), findsWidgets);
      expect(find.text('消息'), findsWidgets);
      expect(find.text('我'), findsWidgets);
      expect(find.text(UITextConstants.bottomNavGuestProfile), findsNothing);
      expect(
        find.descendant(
          of: find.byType(BottomNavigationWidget),
          matching: find.text('精品'),
        ),
        findsOneWidget,
      );
      expect(
        find.descendant(
          of: find.byType(BottomNavigationWidget),
          matching: find.byIcon(CupertinoIcons.plus),
        ),
        findsOneWidget,
      );
      expect(
        find.descendant(
          of: find.byType(BottomNavigationWidget),
          matching: find.text('创作'),
        ),
        findsNothing,
      );
    });

    testWidgets('圈子路由归并到首页频道', (tester) async {
      _suppressExpectedErrors();
      await tester.pumpWidget(_buildShell(AppRoutePaths.circles));
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.byType(MainAppShell), findsOneWidget);
      expect(find.byType(HomePage), findsOneWidget);
    });

    testWidgets('深色模式下底部导航仍展示五栏', (tester) async {
      _suppressExpectedErrors();
      await tester.pumpWidget(_buildDarkShell(AppRoutePaths.home));
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.byType(BottomNavigationWidget), findsOneWidget);
      expect(find.text('首页'), findsWidgets);
      expect(
        find.descendant(
          of: find.byType(BottomNavigationWidget),
          matching: find.text('精品'),
        ),
        findsOneWidget,
      );
    });

    testWidgets('未登录时底部我的栏显示未登录', (tester) async {
      _suppressExpectedErrors();
      await tester.pumpWidget(
        _buildShell(AppRoutePaths.home, authenticated: false),
      );
      await tester.pump(const Duration(milliseconds: 300));

      expect(
        find.descendant(
          of: find.byType(BottomNavigationWidget),
          matching: find.text(UITextConstants.bottomNavGuestProfile),
        ),
        findsOneWidget,
      );
      expect(
        find.descendant(
          of: find.byType(BottomNavigationWidget),
          matching: find.text(AppConceptConstants.profile),
        ),
        findsNothing,
      );
    });

    testWidgets('底部中间加号打开统一动作面板', (tester) async {
      _suppressExpectedErrors();
      await tester.pumpWidget(_buildShell(AppRoutePaths.home));
      await tester.pumpAndSettle();

      await tester.tap(
        find.descendant(
          of: find.byType(BottomNavigationWidget),
          matching: find.byIcon(CupertinoIcons.plus),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text(UITextConstants.createActionWrite), findsOneWidget);
      expect(find.text(UITextConstants.createActionGallery), findsOneWidget);
    });

    testWidgets('底部导航上下留白对称且使用统一语义 token', (tester) async {
      _suppressExpectedErrors();
      tester.view.physicalSize = const Size(1179, 2556);
      tester.view.devicePixelRatio = 3.0;
      tester.view.viewPadding = const FakeViewPadding(bottom: 34);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      addTearDown(tester.view.resetViewPadding);

      await tester.pumpWidget(_buildShell(AppRoutePaths.home));
      await tester.pumpAndSettle();

      final navFinder = find.byType(BottomNavigationWidget);
      final navElement = tester.element(navFinder);
      final navSize = tester.getSize(navFinder);
      final bottomInset =
          tester.view.viewPadding.bottom / tester.view.devicePixelRatio;
      final navHeight = AppSpacing.bottomNavBarHeight(navElement);
      final expectedHeight = navHeight + bottomInset;
      final homeIcon = find.descendant(
        of: navFinder,
        matching: find.byIcon(FluentIcons.home_24_filled),
      );
      final premiumIcon = find.descendant(
        of: navFinder,
        matching: find.byType(AppPremiumMarkIcon),
      );
      final messageIcon = find.descendant(
        of: navFinder,
        matching: find.byType(AppMessagesIcon),
      );
      final profileIcon = find.descendant(
        of: navFinder,
        matching: find.byIcon(FluentIcons.person_circle_24_regular),
      );
      final navTop = tester.getTopLeft(navFinder).dy;
      final iconTop = tester.getTopLeft(homeIcon).dy;
      final iconCenterY = tester.getCenter(homeIcon).dy;

      expect(navSize.height, closeTo(expectedHeight, 0.5));
      final iconToTop = iconTop - navTop;
      expect(iconToTop, greaterThanOrEqualTo(0));
      expect(iconToTop, lessThan(navHeight / 2));
      expect(
        (tester.getCenter(premiumIcon).dy - iconCenterY).abs(),
        lessThan(1),
      );
      expect(
        (tester.getCenter(messageIcon).dy - iconCenterY).abs(),
        lessThan(1),
      );
      expect(
        (tester.getCenter(profileIcon).dy - iconCenterY).abs(),
        lessThan(1),
      );
    });

    testWidgets('底部导航背景与 post 表面色一致', (tester) async {
      _suppressExpectedErrors();
      await tester.pumpWidget(_buildShell(AppRoutePaths.home));
      await tester.pumpAndSettle();

      final navDecoration = tester.widget<DecoratedBox>(
        find
            .descendant(
              of: find.byType(BottomNavigationWidget),
              matching: find.byType(DecoratedBox),
            )
            .first,
      );
      final decoration = navDecoration.decoration as BoxDecoration;
      expect(
        decoration.color,
        SettingsSemanticConstants.conversationSheetCardSurface(false),
      );
      expect(decoration.border, isNull);
    });

    testWidgets('Web 能力下顶部展示安装提示，移动宽度提供下载与分享', (tester) async {
      _suppressExpectedErrors();
      tester.view.physicalSize = const Size(390, 844);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            platformCapabilitiesProvider.overrideWithValue(
              CapabilityProfile.web,
            ),
            authSessionStoreProvider.overrideWithValue(
              const _TestAuthSessionStore(authenticated: true),
            ),
          ],
          child: MaterialApp(
            localizationsDelegates: const [
              AppLocalizations.delegate,
              GlobalMaterialLocalizations.delegate,
              GlobalWidgetsLocalizations.delegate,
              GlobalCupertinoLocalizations.delegate,
            ],
            supportedLocales: const [Locale('zh', 'CN'), Locale('en', 'US')],
            home: MainAppShell(
              currentLocation: AppRoutePaths.home,
              child: const SizedBox.shrink(),
            ),
          ),
        ),
      );
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.text(UITextConstants.webInstallBannerTitle), findsOneWidget);
      expect(
        find.text(UITextConstants.webInstallBannerDownloadApp),
        findsOneWidget,
      );
      expect(
        find.descendant(
          of: find.byType(WebAppInstallBanner),
          matching: find.text(UITextConstants.share),
        ),
        findsOneWidget,
      );
    });

    testWidgets('Web 宽屏展示对应安装包入口', (tester) async {
      _suppressExpectedErrors();
      tester.view.physicalSize = const Size(1280, 900);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            platformCapabilitiesProvider.overrideWithValue(
              CapabilityProfile.web,
            ),
            authSessionStoreProvider.overrideWithValue(
              const _TestAuthSessionStore(authenticated: true),
            ),
          ],
          child: MaterialApp(
            localizationsDelegates: const [
              AppLocalizations.delegate,
              GlobalMaterialLocalizations.delegate,
              GlobalWidgetsLocalizations.delegate,
              GlobalCupertinoLocalizations.delegate,
            ],
            supportedLocales: const [Locale('zh', 'CN'), Locale('en', 'US')],
            home: MainAppShell(
              currentLocation: AppRoutePaths.home,
              child: const SizedBox.shrink(),
            ),
          ),
        ),
      );
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.text(UITextConstants.webInstallBannerTitle), findsOneWidget);
      expect(
        find.text(UITextConstants.webInstallBannerIosPackage),
        findsOneWidget,
      );
      expect(
        find.text(UITextConstants.webInstallBannerAndroidPackage),
        findsOneWidget,
      );
      expect(
        find.text(UITextConstants.webInstallBannerShareInstall),
        findsOneWidget,
      );
    });
  });
}
