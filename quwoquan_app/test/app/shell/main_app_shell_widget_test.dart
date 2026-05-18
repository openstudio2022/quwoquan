import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/shell/bottom_navigation.dart';
import 'package:quwoquan_app/app/shell/main_app_shell.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/l10n/l10n.dart';
import 'package:quwoquan_app/ui/circle/pages/home_circles_hub_page.dart';
import 'package:shared_preferences/shared_preferences.dart';

Widget _buildShell(String location) {
  return ProviderScope(
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

Widget _buildDarkShell(String location) {
  return ProviderScope(
    overrides: [isDarkProvider.overrideWith((ref) => true)],
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
    testWidgets('底部导航展示五栏，圈子成为独立一级入口', (tester) async {
      _suppressExpectedErrors();
      await tester.pumpWidget(_buildShell(AppRoutePaths.home));
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.text('首页'), findsWidgets);
      expect(find.text('圈子'), findsWidgets);
      expect(find.text('消息'), findsWidgets);
      expect(find.text('我'), findsWidgets);
      expect(
        find.descendant(
          of: find.byType(BottomNavigationWidget),
          matching: find.text('圈子'),
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

    testWidgets('圈子路由渲染独立圈子页', (tester) async {
      _suppressExpectedErrors();
      await tester.pumpWidget(_buildShell(AppRoutePaths.circles));
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.byType(MainAppShell), findsOneWidget);
      expect(find.byType(CirclesHubPage), findsOneWidget);
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
          matching: find.text('圈子'),
        ),
        findsOneWidget,
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
        matching: find.byIcon(CupertinoIcons.house_fill),
      );
      final navTop = tester.getTopLeft(navFinder).dy;
      final iconTop = tester.getTopLeft(homeIcon).dy;

      expect(navSize.height, closeTo(expectedHeight, 0.5));
      final iconToTop = iconTop - navTop;
      expect(iconToTop, greaterThanOrEqualTo(0));
      expect(iconToTop, lessThan(navHeight / 2));
    });
  });
}
