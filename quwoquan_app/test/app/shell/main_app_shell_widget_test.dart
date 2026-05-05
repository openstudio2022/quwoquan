import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/shell/bottom_navigation.dart';
import 'package:quwoquan_app/app/shell/main_app_shell.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/l10n/l10n.dart';
import 'package:quwoquan_app/ui/assistant/pages/personal_assistant_conversation_page.dart';
import 'package:quwoquan_app/ui/circle/pages/circles_page.dart';
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
    testWidgets('底部导航展示四栏，圈子保留在首页一级 Tab', (tester) async {
      _suppressExpectedErrors();
      await tester.pumpWidget(_buildShell(AppRoutePaths.home));
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.text('首页'), findsWidgets);
      expect(find.text('私助'), findsWidgets);
      expect(find.text('趣信'), findsWidgets);
      expect(find.text('我的'), findsWidgets);
      expect(
        find.descendant(
          of: find.byType(BottomNavigationWidget),
          matching: find.text('圈子'),
        ),
        findsNothing,
      );
      expect(find.text('圈子'), findsWidgets);
    });

    testWidgets('圈子路由渲染独立圈子页', (tester) async {
      _suppressExpectedErrors();
      await tester.pumpWidget(_buildShell(AppRoutePaths.circles));
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.byType(MainAppShell), findsOneWidget);
      expect(find.byType(CirclesPage), findsOneWidget);
    });

    testWidgets('深色模式下底部导航仍展示四栏', (tester) async {
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
        findsNothing,
      );
    });

    testWidgets('assistant 路由也能在主壳中渲染', (tester) async {
      _suppressExpectedErrors();
      await tester.pumpWidget(_buildShell(AppRoutePaths.assistant));
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.byType(MainAppShell), findsOneWidget);
      expect(find.byType(PersonalAssistantConversationPage), findsOneWidget);
    });

    testWidgets('助理主入口隐藏底部导航并直接渲染找私助', (tester) async {
      _suppressExpectedErrors();
      await tester.pumpWidget(_buildShell(AppRoutePaths.assistant));
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.byType(PersonalAssistantConversationPage), findsOneWidget);
      expect(find.byType(BottomNavigationWidget), findsNothing);
    });
  });
}
