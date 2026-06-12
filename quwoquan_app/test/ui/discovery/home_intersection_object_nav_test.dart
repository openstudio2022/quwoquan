import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/ui/discovery/pages/home_page.dart';
import 'package:quwoquan_app/ui/discovery/widgets/intersection_spotlight_module.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// A2：发现交集对象卡点击 → 按对象类型路由（路由来自 metadata codegen）。
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
                body: Center(
                  child: Text('HOMEPAGE:${state.pathParameters['id']}'),
                ),
              ),
            ),
            GoRoute(
              path: '/circle/:id',
              builder: (context, state) => Scaffold(
                body: Center(
                  child: Text('CIRCLE:${state.pathParameters['id']}'),
                ),
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
    await tester.pump(const Duration(milliseconds: 300));

    // recommend 频道交集（getFeedIntersections，contract fixture 同源）：
    // person「林清越」→ /user/fixture_user_lin。
    final personCard = find.text('林清越');
    expect(personCard, findsWidgets);

    await tester.tap(personCard.first, warnIfMissed: false);
    await tester.pumpAndSettle();

    expect(find.text('USER:fixture_user_lin'), findsOneWidget);
  });

  testWidgets('点击概率交集对象卡（推荐）→ 跳 /user/{id}（metadata 路由）', (tester) async {
    _suppressExpectedErrors();
    await tester.pumpWidget(_buildApp());
    await tester.pump(const Duration(milliseconds: 300));
    await tester.pump(const Duration(milliseconds: 300));

    // recommend 频道含概率（affinity）交集「陆衡」→ 标「推荐」，点卡仍进对象页。
    // fixture seed（intersection_core）recommend 候选窗与 intersectionFeedLimit=4 对齐，
    // 保证 affinity 代表卡（陆衡）始终入窗。
    final spotlightRail = find.descendant(
      of: find.byKey(IntersectionSpotlightModule.moduleKey),
      matching: find.byType(Scrollable),
    );
    expect(spotlightRail, findsWidgets);
    if (find.text('陆衡').evaluate().isEmpty) {
      await tester.drag(
        spotlightRail.first,
        const Offset(-160, 0),
        warnIfMissed: false,
      );
      await tester.pump(const Duration(milliseconds: 300));
    }

    final affinityCard = find.text('陆衡');
    expect(affinityCard, findsWidgets);

    await tester.tap(affinityCard.first, warnIfMissed: false);
    await tester.pumpAndSettle();

    expect(find.text('USER:fixture_user_lu'), findsOneWidget);
  });
}
