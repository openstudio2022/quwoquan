import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/ui/discovery/pages/home_page.dart';
import 'package:quwoquan_app/ui/discovery/widgets/unified_object_card.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// A2：今日交集对象卡点击 → 按对象类型路由（路由来自 metadata codegen）。
Widget _buildApp() {
  return ProviderScope(
    child: ScreenUtilInit(
      designSize: const Size(393, 852),
      child: MaterialApp.router(
        routerConfig: GoRouter(
          initialLocation: '/',
          routes: [
            GoRoute(
              path: '/',
              builder: (context, state) =>
                  const Scaffold(body: HomePage(routeLocation: '/')),
            ),
            GoRoute(
              path: '/user/:username',
              builder: (context, state) => Scaffold(
                body: Center(
                  child: Text('USER:${state.pathParameters['username']}'),
                ),
              ),
            ),
            GoRoute(
              path: '/homepages/:id',
              builder: (context, state) => Scaffold(
                body: Center(child: Text('HOMEPAGE:${state.pathParameters['id']}')),
              ),
            ),
            GoRoute(
              path: '/circle/:id',
              builder: (context, state) => Scaffold(
                body: Center(child: Text('CIRCLE:${state.pathParameters['id']}')),
              ),
            ),
            GoRoute(path: '/search', builder: (_, _) => const SizedBox()),
          ],
        ),
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

  testWidgets('点击「人」对象卡 → 跳 /user/{id}（metadata 路由）', (tester) async {
    _suppressExpectedErrors();
    await tester.pumpWidget(_buildApp());
    await tester.pump(const Duration(milliseconds: 300));

    // recommend 默认频道展示今日交集对象卡（mock m1 = 关注作者 u1）。
    expect(find.byType(UnifiedObjectCard), findsWidgets);
    final personCard = find.descendant(
      of: find.byType(UnifiedObjectCard),
      matching: find.text('你和 TA 都来自新东方校友圈'),
    );
    expect(personCard, findsOneWidget);

    await tester.tap(personCard);
    await tester.pumpAndSettle();

    expect(find.text('USER:u1'), findsOneWidget);
  });

  testWidgets('点击「地点」对象卡 → 跳 /homepages/{id}（metadata 路由）', (tester) async {
    _suppressExpectedErrors();
    await tester.pumpWidget(_buildApp());
    await tester.pump(const Duration(milliseconds: 300));

    final placeCard = find.descendant(
      of: find.byType(UnifiedObjectCard),
      matching: find.text('你和 TA 都去过 西湖'),
    );
    expect(placeCard, findsOneWidget);

    await tester.tap(placeCard);
    await tester.pumpAndSettle();

    expect(find.text('HOMEPAGE:hp_west_lake'), findsOneWidget);
  });
}
